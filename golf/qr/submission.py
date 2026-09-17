"""
The whole submission pipeline in one place: round -> URL -> QR -> NES bytes.

This is exactly what the ROM routine has to reproduce, so it is also the
oracle the 6502 port gets tested against, and the thing the table exporter
will dump.
"""

from dataclasses import dataclass

from golf.qr import nes
from golf.qr.encoder import QrMatrix, Stages, encode_stages
from golf.qr.payload import RoundPayload

#: The mask the ROM hard-wires, so it can skip the spec's penalty scoring.
#:
#: Chosen by `golf-qr-validate` over two sweeps on different seeds. zxing-cpp
#: — the stand-in for a phone scanner — decoded all 17,050 images under every
#: mask with zero failures, so every mask is viable. OpenCV's stricter
#: detector is what separates them, and mask 5 came out best in both runs:
#: pooled, it fails 0.80% of OpenCV attempts against 1.34% and 1.63% for the
#: two masks it was compared against head to head.
#:
#: The spec's own penalty heuristic is *not* predictive here — it prefers mask
#: 2, which measured no better. See `docs/scorecard_qr.md`.
FIXED_MASK = 5


@dataclass(frozen=True)
class Submission:
    """Everything the QR screen is built from."""

    url: str
    payload: bytes
    stages: Stages
    chr_data: bytes
    nametable: bytes

    @property
    def matrix(self) -> QrMatrix:
        return self.stages.matrix

    @property
    def mask(self) -> int:
        return self.stages.mask


def from_url(url: str, mask: int = FIXED_MASK, base_tile: int = 0) -> Submission:
    stages = encode_stages(url, mask)
    rows = stages.matrix.rows()
    return Submission(
        url=url,
        payload=b"",
        stages=stages,
        chr_data=nes.build_chr(),
        nametable=nes.build_nametable(rows, base_tile),
    )


def build(
    round_payload: RoundPayload,
    key: bytes,
    mask: int = FIXED_MASK,
    base_tile: int = 0,
) -> Submission:
    payload = round_payload.to_bytes(key)
    url = round_payload.to_url(key)
    submission = from_url(url, mask, base_tile)
    return Submission(
        url=url,
        payload=payload,
        stages=submission.stages,
        chr_data=submission.chr_data,
        nametable=submission.nametable,
    )
