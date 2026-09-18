"""
PatchStack: an ordered list of built patches, applied to a base ROM in memory.

A stack is what a finished ROM is made of - the course, the code it needs, and
the gameplay patches on top - in the order they are listed. Building one checks
three things a plain sequence of `apply` calls does not:

- **The base ROM.** By default it must be the vanilla US ROM
  (`rom_utils.US_ROM_SHA1`); pass `base_sha1=None` to build on another base.
- **Requirements.** Before a step is applied, every patch in its `requires`
  must already be applied - by an earlier step, or in the base. The stack never
  adds or reorders steps.
- **Overlaps.** Every write is attributed to the step making it, and a step
  that writes a byte an earlier step wrote is an error, even when the value is
  the same. Patches that check the bytes they replace catch most conflicts
  themselves; this also catches the writes that do not check, such as course
  data and the scorecard QR image.

See docs/patch_stack.md.
"""

import hashlib
from array import array
from collections.abc import Sequence
from dataclasses import dataclass

from golf.core import rom_utils
from golf.core.ips import diff as ips_diff
from golf.core.rom_writer import RomWriter

from .base import PatchError, ROMPatch


class StackError(PatchError):
    """Raised when a stack cannot be built."""


@dataclass(frozen=True)
class StackBuild:
    """A built stack: the patched ROM file, and what each step wrote."""

    rom: bytes
    #: step name -> the [start, end) PRG offset ranges that step wrote
    regions: dict[str, list[tuple[int, int]]]


def describe_prg(prg_offset: int) -> str:
    """A PRG offset as bank, CPU address and offset, for error messages."""
    bank, cpu_addr = rom_utils.prg_to_bank_and_cpu(prg_offset)
    return f"bank {bank} ${cpu_addr:04X} (PRG 0x{prg_offset:05X})"


class _TrackingWriter(RomWriter):
    """A RomWriter that records which step wrote each byte, and refuses a
    write to a byte an earlier step already wrote."""

    def __init__(self, base: bytes, names: Sequence[str]):
        self._load(base, None)
        self._names = list(names)
        self._owners = array("H", bytes(2 * len(self.rom_data)))  # 0 = unwritten
        self._step = 0

    def begin_step(self, index: int) -> None:
        self._step = index + 1

    def write_prg(self, prg_offset: int, data: bytes) -> None:
        start = self.prg_start + prg_offset
        owners = self._owners
        for i in range(start, start + len(data)):
            previous = owners[i]
            if previous and previous != self._step:
                raise StackError(
                    f"step '{self._names[self._step - 1]}' writes "
                    f"{describe_prg(i - self.prg_start)}, which step "
                    f"'{self._names[previous - 1]}' already wrote"
                )
        for i in range(start, start + len(data)):
            owners[i] = self._step
        super().write_prg(prg_offset, data)

    def regions(self) -> dict[str, list[tuple[int, int]]]:
        result: dict[str, list[tuple[int, int]]] = {name: [] for name in self._names}
        current, run_start = 0, 0
        for i, owner in enumerate([*self._owners, 0]):
            if owner != current:
                if current:
                    result[self._names[current - 1]].append(
                        (run_start - self.prg_start, i - self.prg_start)
                    )
                current, run_start = owner, i
        return result


class PatchStack:
    """An ordered list of built patches."""

    def __init__(
        self,
        steps: Sequence[ROMPatch],
        base_sha1: str | None = rom_utils.US_ROM_SHA1,
    ):
        names = [step.name for step in steps]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise StackError(f"duplicate step names: {', '.join(duplicates)}")
        self.steps = list(steps)
        self.base_sha1 = base_sha1

    def build(self, base: bytes) -> StackBuild:
        """Apply every step to a copy of `base`. The base is not modified."""
        self._check_base(base)
        writer = _TrackingWriter(base, [step.name for step in self.steps])
        for index, step in enumerate(self.steps):
            self._check_requirements(index, step, writer)
            writer.begin_step(index)
            try:
                step.apply(writer)
            except StackError:
                raise
            except PatchError as error:
                raise StackError(f"step '{step.name}': {error}") from error
        return StackBuild(rom=bytes(writer.rom_data), regions=writer.regions())

    def ips(self, base: bytes) -> bytes:
        """The IPS patch that turns `base` into this stack's build."""
        return ips_diff(base, self.build(base).rom)

    def _check_base(self, base: bytes) -> None:
        if self.base_sha1 is None:
            return
        actual = hashlib.sha1(base).hexdigest()
        if actual != self.base_sha1:
            raise StackError(
                f"base ROM SHA-1 is {actual}, expected {self.base_sha1}; "
                "pass base_sha1=None to build on a different base"
            )

    def _check_requirements(
        self, index: int, step: ROMPatch, writer: RomWriter
    ) -> None:
        missing = step.missing_requirements(writer)
        if not missing:
            return
        later = {s.name for s in self.steps[index + 1 :]}
        problems = [
            f"{required.name} ({'listed after it' if required.name in later else 'not in the stack'})"
            for required in missing
        ]
        raise StackError(f"step '{step.name}' requires {', '.join(problems)}")

    def __repr__(self) -> str:
        return f"PatchStack(steps={[step.name for step in self.steps]!r})"
