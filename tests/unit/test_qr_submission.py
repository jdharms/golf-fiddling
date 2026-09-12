"""
The fixed mask, held to the standard that justified choosing it.

Every capture condition the validation harness simulates, both decoders, a
batch of random rounds. This is the test that fails if a future change to the
payload layout, the URL prefix, or the screen placement quietly makes the
fixed-mask decision unsafe.
"""

import random

import pytest

from golf.qr import capture, sample, submission
from golf.qr.decode import DECODERS
from golf.qr.payload import RoundPayload, verify
from golf.qr.render import render_screen

#: OpenCV's binarizer cannot handle the scanline simulation under any mask —
#: it failed 100% of the time on all eight in the sweep, while zxing-cpp read
#: every one. Excluded from the both-decoders assertion below and asserted
#: separately for zxing only.
OPENCV_HOSTILE = {"scanlines"}


@pytest.fixture(scope="module")
def submissions() -> list[submission.Submission]:
    rng = random.Random(4242)
    key = sample.random_key(rng)
    return [submission.build(sample.random_round(rng), key) for _ in range(8)]


def test_fixed_mask_is_recorded() -> None:
    assert 0 <= submission.FIXED_MASK <= 7


def test_build_produces_a_consistent_submission(submissions) -> None:
    for item in submissions:
        assert item.mask == submission.FIXED_MASK
        assert len(item.chr_data) == 256
        assert len(item.nametable) == 361
        assert item.stages.text == item.url.encode()


def test_payload_in_a_submission_verifies() -> None:
    rng = random.Random(7)
    key = sample.random_key(rng)
    item = submission.build(sample.random_round(rng), key)
    assert verify(item.payload, key)
    parsed, _ = RoundPayload.from_url(item.url)
    assert parsed.body() == item.payload[:32]


def test_from_url_matches_build(submissions) -> None:
    for item in submissions:
        assert submission.from_url(item.url).matrix.rows() == item.matrix.rows()


@pytest.mark.parametrize(
    "degradation",
    [d for d in capture.DEGRADATIONS if d.name not in OPENCV_HOSTILE],
    ids=lambda d: d.name,
)
@pytest.mark.parametrize("decoder", sorted(DECODERS))
def test_fixed_mask_survives_capture(
    degradation: capture.Degradation, decoder: str, submissions
) -> None:
    for item in submissions:
        image = degradation.apply(render_screen(item.matrix, scale=1))
        assert DECODERS[decoder](image) == item.url, (
            f"{degradation.name}, {decoder}, {item.url}"
        )


@pytest.mark.parametrize(
    "degradation",
    [d for d in capture.DEGRADATIONS if d.name in OPENCV_HOSTILE],
    ids=lambda d: d.name,
)
def test_opencv_hostile_conditions_still_decode_with_zxing(
    degradation: capture.Degradation, submissions
) -> None:
    for item in submissions:
        image = degradation.apply(render_screen(item.matrix, scale=1))
        assert DECODERS["zxing"](image) == item.url, f"{degradation.name}, {item.url}"


def test_package_does_not_import_dev_only_decoders() -> None:
    """
    zxing-cpp and OpenCV are dev dependencies, so the shipped package must not
    reach them. Guards against a stray import in `golf/qr/__init__.py` or any
    module the submission path pulls in.
    """
    import subprocess
    import sys

    script = (
        "import sys, golf.qr, golf.qr.submission, golf.qr.render, golf.qr.capture; "
        "bad = [m for m in ('cv2', 'zxingcpp', 'qrcode') if m in sys.modules]; "
        "print(bad)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]", result.stdout
