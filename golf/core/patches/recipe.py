"""
Recipes: a PatchStack written down as JSON.

    {
      "base_sha1": null,
      "steps": [
        {"patch": "multi_bank_lookup"},
        {"patch": "course", "course": "courses/japan"},
        {"patch": "seeded_wind", "seed": "abc"}
      ]
    }

`patch` names a patch type in the registry (`registry.PATCH_SPECS`); the other
keys are its parameters, checked against its parameter dataclass. Paths are
relative to the recipe file. `base_sha1` is optional: omitted means the vanilla
US ROM, null means any base.

`parse_step_arg` reads the same steps from `golf-patch -p ID:key=value,...`.
See docs/patch_stack.md.
"""

import json
import os
import types
import typing
from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path

from golf.core import rom_utils
from golf.core.course_validation import InvalidTileError
from golf.core.rom_writer import BankOverflowError

from .base import PatchError, ROMPatch
from .registry import PATCH_SPECS, BuildContext, PatchSpec
from .stack import PatchStack


class RecipeError(ValueError):
    """Raised for a recipe or step that cannot be read or built."""


def get_spec(patch_id: str) -> PatchSpec:
    try:
        return PATCH_SPECS[patch_id]
    except KeyError:
        raise RecipeError(
            f"unknown patch type {patch_id!r}; known types: {', '.join(PATCH_SPECS)}"
        ) from None


# --- Parameters -----------------------------------------------------------------


def _optional_inner(hint):
    """The X of `X | None`, or None if `hint` is not optional."""
    if typing.get_origin(hint) in (types.UnionType, typing.Union):
        args = [arg for arg in typing.get_args(hint) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return None


def _type_name(hint) -> str:
    inner = _optional_inner(hint)
    if inner is not None:
        return f"{_type_name(inner)} or null"
    if typing.get_origin(hint) is list:
        return f"list of {_type_name(typing.get_args(hint)[0])}"
    return {int: "integer", str: "string", bool: "boolean", Path: "path"}.get(hint, str(hint))


def _convert(value, hint, base_dir: Path, where: str):
    inner = _optional_inner(hint)
    if inner is not None:
        return None if value is None else _convert(value, inner, base_dir, where)

    if hint is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
    elif hint is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return int(value, 0)
            except ValueError:
                pass
    elif hint is str:
        if isinstance(value, str):
            return value
    elif hint is Path:
        if isinstance(value, str) and value:
            path = Path(value)
            return path if path.is_absolute() else base_dir / path
    elif typing.get_origin(hint) is list:
        item = typing.get_args(hint)[0]
        if isinstance(value, str) and item is str:
            # `golf-patch -p` has no list syntax, and splits steps on commas
            value = value.split()
        if isinstance(value, list):
            return [_convert(v, item, base_dir, f"{where}[{i}]") for i, v in enumerate(value)]
    raise RecipeError(f"{where}: expected {_type_name(hint)}, got {value!r}")


def _to_json(value, hint, base_dir: Path):
    if value is None:
        return None
    inner = _optional_inner(hint)
    if inner is not None:
        return _to_json(value, inner, base_dir)
    if hint is Path:
        return Path(os.path.relpath(Path(value).absolute(), Path(base_dir).absolute())).as_posix()
    if typing.get_origin(hint) is list:
        item = typing.get_args(hint)[0]
        return [_to_json(v, item, base_dir) for v in value]
    return value


def describe_params(spec: PatchSpec) -> str:
    """A patch type's parameters, for --list and error messages."""
    hints = typing.get_type_hints(spec.params)
    parts = []
    for f in fields(spec.params):
        text = f"{f.name} ({_type_name(hints[f.name])}"
        if f.default is not MISSING and f.default is not None:
            text += f", default {f.default!r}"
        elif f.default is MISSING:
            text += ", required"
        parts.append(text + ")")
    return ", ".join(parts)


def parse_params(spec: PatchSpec, raw: dict, base_dir: Path, where: str):
    """Build a patch type's parameter dataclass from JSON-style values."""
    hints = typing.get_type_hints(spec.params)
    known = {f.name: f for f in fields(spec.params)}
    unknown = sorted(set(raw) - set(known))
    if unknown:
        takes = describe_params(spec) or "no parameters"
        raise RecipeError(f"{where}: unknown parameter(s) {', '.join(unknown)}; {spec.id} takes {takes}")
    values = {}
    for name, f in known.items():
        if name in raw:
            values[name] = _convert(raw[name], hints[name], base_dir, f"{where}.{name}")
        elif f.default is MISSING:
            raise RecipeError(f"{where}: missing required parameter {name!r}")
    return spec.params(**values)


# --- Steps and recipes ------------------------------------------------------------


@dataclass(frozen=True)
class RecipeStep:
    """One step: a patch type and its parameters."""

    patch: str
    params: object

    @classmethod
    def from_dict(cls, data, base_dir: Path, where: str = "step") -> "RecipeStep":
        if not isinstance(data, dict) or "patch" not in data:
            raise RecipeError(f"{where}: a step is an object with a 'patch' key")
        raw = dict(data)
        patch_id = raw.pop("patch")
        spec = get_spec(patch_id)
        return cls(patch_id, parse_params(spec, raw, Path(base_dir), f"{where} ({patch_id})"))

    def to_dict(self, base_dir: Path) -> dict:
        hints = typing.get_type_hints(type(self.params))
        out: dict = {"patch": self.patch}
        for f in fields(self.params):
            value = getattr(self.params, f.name)
            if f.default is not MISSING and value == f.default:
                continue
            out[f.name] = _to_json(value, hints[f.name], Path(base_dir))
        return out


@dataclass(frozen=True)
class BuiltStep:
    """A step's patch, built, with what it was built from."""

    spec: PatchSpec
    params: object
    patch: ROMPatch

    def report(self) -> list[str]:
        return self.spec.report(self.params, self.patch)


@dataclass
class Recipe:
    """An ordered list of steps, and the base ROM they build on."""

    steps: list[RecipeStep] = field(default_factory=list)
    base_sha1: str | None = rom_utils.US_ROM_SHA1

    @classmethod
    def from_dict(cls, data, base_dir: Path) -> "Recipe":
        if not isinstance(data, dict):
            raise RecipeError("a recipe is a JSON object")
        unknown = sorted(set(data) - {"base_sha1", "steps"})
        if unknown:
            raise RecipeError(f"unknown recipe key(s): {', '.join(unknown)}")
        steps = data.get("steps")
        if not isinstance(steps, list):
            raise RecipeError("a recipe needs a 'steps' list")
        base_sha1 = data.get("base_sha1", rom_utils.US_ROM_SHA1)
        if base_sha1 is not None and not isinstance(base_sha1, str):
            raise RecipeError("base_sha1 must be a SHA-1 hex string or null")
        return cls(
            [RecipeStep.from_dict(step, base_dir, f"steps[{i}]") for i, step in enumerate(steps)],
            base_sha1,
        )

    @classmethod
    def load(cls, path: Path) -> "Recipe":
        path = Path(path)
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            raise RecipeError(f"{path}: {error}") from error
        return cls.from_dict(data, path.parent)

    def to_dict(self, base_dir: Path) -> dict:
        out: dict = {}
        if self.base_sha1 != rom_utils.US_ROM_SHA1:
            out["base_sha1"] = self.base_sha1
        out["steps"] = [step.to_dict(base_dir) for step in self.steps]
        return out

    def save(self, path: Path) -> None:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(path.parent), indent=2) + "\n")

    def build_steps(self, base: bytes) -> list[BuiltStep]:
        """Build every step's patch. `base` is the ROM factories may read."""
        context = BuildContext(base)
        built = []
        for index, step in enumerate(self.steps):
            spec = get_spec(step.patch)
            try:
                patch = spec.build(context, step.params)
            except (
                ValueError,
                OSError,
                PatchError,
                BankOverflowError,
                InvalidTileError,
            ) as error:
                raise RecipeError(f"steps[{index}] ({step.patch}): {error}") from error
            if patch.name != step.patch:
                raise RecipeError(
                    f"steps[{index}]: patch type {step.patch!r} built a patch named {patch.name!r}"
                )
            built.append(BuiltStep(spec, step.params, patch))
        return built

    def stack(self, base: bytes) -> PatchStack:
        """The PatchStack of this recipe's patches."""
        return PatchStack([b.patch for b in self.build_steps(base)], base_sha1=self.base_sha1)


def parse_step_arg(text: str, base_dir: Path) -> RecipeStep:
    """A step from `ID` or `ID:key=value,key=value`, as `golf-patch -p` takes."""
    patch_id, _, rest = text.partition(":")
    raw: dict = {}
    if rest:
        for item in rest.split(","):
            key, equals, value = item.partition("=")
            if not equals or not key.strip():
                raise RecipeError(
                    f"-p {text!r}: parameters are key=value pairs separated by commas"
                )
            raw[key.strip()] = value
    return RecipeStep.from_dict({"patch": patch_id.strip(), **raw}, base_dir, where=f"-p {patch_id}")
