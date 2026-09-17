# Scorecard QR

The end-of-round submission QR code. Full design and rationale: `docs/scorecard_qr.md`.

## The Python package is the oracle

`golf/qr/` is the **reference implementation for the 6502 port**:

- `payload.py`, `halfsiphash.py` - payload and MAC
- `encoder.py`, `galois.py` - a version 5-M QR encoder hard-wired to that one version
- `nes.py` - the NES tile/nametable pipeline
- `render.py` - PNG rendering
- `capture.py`, `decode.py` - simulated capture conditions and decoders
- `tables.py` - the ROM table export (`golf-qr-tables`, checked-in output in `data/qr/`)

Rules that follow from being the oracle:

- Every stage is exposed individually (`encoder.encode_stages`) so the port can be
  compared stage by stage.
- Every ROM table is *derived* from those stages, never transcribed beside them.
- Every constant the ROM bakes in is asserted in `tests/unit/test_qr_*.py`.
- Correctness is pinned two ways: module for module against the independent `qrcode`
  package, and by decoding real renders with zxing-cpp and OpenCV.

## The 6502 port

`golf/qr/port/` holds assembly sources, assembled by `golf/core/asm6502.py` against
`port/layout.py` and run under py65 by `port/sim.py`. They are differentially tested
stage by stage against the oracle in `tests/unit/test_qr_port.py`.

`port/sim.py` also models the slice of the PPU that the display layer (`display.s`) uses,
and stubs the fixed-bank routines it calls, so `tests/unit/test_qr_display.py` can check
the finished screen, and decode the QR, out of simulated video memory.

## Tools

- `golf-qr-preview` - build a payload, encode it as the ROM will, render the NES screen
- `golf-qr-validate` - sweep masks x rounds x capture conditions x decoders; this is what
  justifies a fixed mask instead of spec penalty scoring
- `golf-qr-tables` - export the ROM tables
- `golf-qr-port` - assemble the port and report per-routine sizes against the bank 2 budget
- `golf-qr-credentials` - write a build's seed ID, player IDs and secret MAC keys; the
  `scorecard_qr` step of `golf-patch` installs the QR screen with them unfilled, and the
  `qr_credentials` step writes them in
