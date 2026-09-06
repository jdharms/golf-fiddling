# Vanilla Course Terrain Data Locations

> **Note**: This document was written by Claude based on investigation requested by jdharms.

Byte ranges of the three vanilla courses' compressed terrain data in `nes_open_us.nes`, derived from the terrain pointer tables (`$DBC1` start / `$DC2D` end) in the fixed bank, cross-referenced against the `TerrainBankPerCourse` table at `$DBBE` (Japan=bank 0, US=bank 1, UK=bank 2).

File offsets assume the standard 16-byte iNES header (no trainer) present in `nes_open_us.nes`.

## Per-Course Summary

| Course | Bank | CPU range | PRG offset | File offset (in .nes) | Actual data used | Max available (bank boundary) |
|---|---|---|---|---|---|---|
| Japan | 0 | $8000–$A1F6 | 0x00000–0x021F6 | 0x000010–0x002206 | 8,695 B | 8,766 B (to $A23D) |
| US | 1 | $8000–$A19E | 0x04000–0x0619E | 0x004010–0x0061AE | 8,607 B | 8,678 B (to $A1E5) |
| UK | 2 | $837F–$A50C | 0x0837F–0x0A50C | 0x00838F–0x00A51C | 8,590 B | 8,661 B (to $A553) |

The "max available" end address is the boundary before the fixed lookup tables that must be preserved in each bank (see `PackedCourseWriter` constraints in `CLAUDE.md`). If a course is stripped entirely, the reclaimable region is the **max available** span, not just the currently-used bytes — e.g. dropping UK frees `$837F`–`$A553` in bank 2, file offset `0x00838F`–`0x00A563` (8,661 bytes), regardless of how much the vanilla UK data actually used.

Each hole's terrain is immediately followed by that hole's attribute data before the next hole starts, so the per-hole end pointer below is not a hard free/used boundary — treat the whole-bank span above as the safe reclaimable block once a course is removed.

## Multi-Course Mirroring

Applying `COURSE2_MIRROR_PATCH` and `COURSE3_MIRROR_PATCH` (`golf/core/patches/multi_bank.py`) makes the US and UK course slots mirror Japan's hole data. In that configuration, the terrain data regions of banks 1 ($8000–$A1E5) and 2 ($837F–$A553) are free for new code/data — combined that's 8,678 + 8,661 = **17,339 bytes** of switchable-bank space, useful for something like a randomizer that only ever needs one course's worth of terrain resident at a time. Only those regions are reclaimable: the lookup tables and code outside them (bank 1 from $A1E6, bank 2 at $8000–$837E and from $A554) are still live and must be preserved.

## Per-Hole Detail

### Japan (bank 0)

| Hole | CPU range | PRG offset | File offset | Size |
|---|---|---|---|---|
| 1 | $8000–$81FA | 0x00000–0x001FA | 0x000010–0x00020A | 507 |
| 2 | $8236–$83FE | 0x00236–0x003FE | 0x000246–0x00040E | 457 |
| 3 | $842E–$8629 | 0x0042E–0x00629 | 0x00043E–0x000639 | 508 |
| 4 | $866B–$87FF | 0x0066B–0x007FF | 0x00067B–0x00080F | 405 |
| 5 | $882F–$89BB | 0x0082F–0x009BB | 0x00083F–0x0009CB | 397 |
| 6 | $89F1–$8B5A | 0x009F1–0x00B5A | 0x000A01–0x000B6A | 362 |
| 7 | $8B8A–$8D62 | 0x00B8A–0x00D62 | 0x000B9A–0x000D72 | 473 |
| 8 | $8DA4–$8EF0 | 0x00DA4–0x00EF0 | 0x000DB4–0x000F00 | 333 |
| 9 | $8F20–$90AF | 0x00F20–0x010AF | 0x000F30–0x0010BF | 400 |
| 10 | $90E5–$92D6 | 0x010E5–0x012D6 | 0x0010F5–0x0012E6 | 498 |
| 11 | $9306–$949A | 0x01306–0x0149A | 0x001316–0x0014AA | 405 |
| 12 | $94CA–$969F | 0x014CA–0x0169F | 0x0014DA–0x0016AF | 470 |
| 13 | $96E1–$987C | 0x016E1–0x0187C | 0x0016F1–0x00188C | 412 |
| 14 | $98AC–$99E9 | 0x018AC–0x019E9 | 0x0018BC–0x0019F9 | 318 |
| 15 | $9A1F–$9BD6 | 0x01A1F–0x01BD6 | 0x001A2F–0x001BE6 | 440 |
| 16 | $9C0C–$9D5B | 0x01C0C–0x01D5B | 0x001C1C–0x001D6B | 336 |
| 17 | $9D8B–$9F74 | 0x01D8B–0x01F74 | 0x001D9B–0x001F84 | 490 |
| 18 | $9FB0–$A1F6 | 0x01FB0–0x021F6 | 0x001FC0–0x002206 | 583 |

### US (bank 1)

| Hole | CPU range | PRG offset | File offset | Size |
|---|---|---|---|---|
| 1 | $8000–$81E9 | 0x04000–0x041E9 | 0x004010–0x0041F9 | 490 |
| 2 | $821F–$83EA | 0x0421F–0x043EA | 0x00422F–0x0043FA | 460 |
| 3 | $842C–$85C1 | 0x0442C–0x045C1 | 0x00443C–0x0045D1 | 406 |
| 4 | $85F7–$87A3 | 0x045F7–0x047A3 | 0x004607–0x0047B3 | 429 |
| 5 | $87D3–$8935 | 0x047D3–0x04935 | 0x0047E3–0x004945 | 355 |
| 6 | $896B–$8B18 | 0x0496B–0x04B18 | 0x00497B–0x004B28 | 430 |
| 7 | $8B4E–$8CA8 | 0x04B4E–0x04CA8 | 0x004B5E–0x004CB8 | 347 |
| 8 | $8CD8–$8EB0 | 0x04CD8–0x04EB0 | 0x004CE8–0x004EC0 | 473 |
| 9 | $8EF2–$90C9 | 0x04EF2–0x050C9 | 0x004F02–0x0050D9 | 472 |
| 10 | $9105–$9255 | 0x05105–0x05255 | 0x005115–0x005265 | 337 |
| 11 | $9285–$9443 | 0x05285–0x05443 | 0x005295–0x005453 | 447 |
| 12 | $947F–$9625 | 0x0547F–0x05625 | 0x00548F–0x005635 | 423 |
| 13 | $9661–$9864 | 0x05661–0x05864 | 0x005671–0x005874 | 516 |
| 14 | $98A0–$9A02 | 0x058A0–0x05A02 | 0x0058B0–0x005A12 | 355 |
| 15 | $9A32–$9BFB | 0x05A32–0x05BFB | 0x005A42–0x005C0B | 458 |
| 16 | $9C37–$9DB7 | 0x05C37–0x05DB7 | 0x005C47–0x005DC7 | 385 |
| 17 | $9DE7–$9F70 | 0x05DE7–0x05F70 | 0x005DF7–0x005F80 | 394 |
| 18 | $9FAC–$A19E | 0x05FAC–0x0619E | 0x005FBC–0x0061AE | 499 |

### UK (bank 2)

| Hole | CPU range | PRG offset | File offset | Size |
|---|---|---|---|---|
| 1 | $837F–$8512 | 0x0837F–0x08512 | 0x00838F–0x008522 | 404 |
| 2 | $8548–$8700 | 0x08548–0x08700 | 0x008558–0x008710 | 441 |
| 3 | $8736–$8904 | 0x08736–0x08904 | 0x008746–0x008914 | 463 |
| 4 | $8946–$8AB4 | 0x08946–0x08AB4 | 0x008956–0x008AC4 | 367 |
| 5 | $8AE4–$8CB8 | 0x08AE4–0x08CB8 | 0x008AF4–0x008CC8 | 469 |
| 6 | $8CFA–$8E66 | 0x08CFA–0x08E66 | 0x008D0A–0x008E76 | 365 |
| 7 | $8EA2–$9002 | 0x08EA2–0x09002 | 0x008EB2–0x009012 | 353 |
| 8 | $9038–$91B1 | 0x09038–0x091B1 | 0x009048–0x0091C1 | 378 |
| 9 | $91E1–$93FD | 0x091E1–0x093FD | 0x0091F1–0x00940D | 541 |
| 10 | $9445–$95DA | 0x09445–0x095DA | 0x009455–0x0095EA | 406 |
| 11 | $9610–$9821 | 0x09610–0x09821 | 0x009620–0x009831 | 530 |
| 12 | $9863–$99D0 | 0x09863–0x099D0 | 0x009873–0x0099E0 | 366 |
| 13 | $9A00–$9BE3 | 0x09A00–0x09BE3 | 0x009A10–0x009BF3 | 484 |
| 14 | $9C25–$9D7F | 0x09C25–0x09D7F | 0x009C35–0x009D8F | 347 |
| 15 | $9DAF–$9F9A | 0x09DAF–0x09F9A | 0x009DBF–0x009FAA | 492 |
| 16 | $9FD6–$A18C | 0x09FD6–0x0A18C | 0x009FE6–0x00A19C | 439 |
| 17 | $A1CE–$A321 | 0x0A1CE–0x0A321 | 0x00A1DE–0x00A331 | 340 |
| 18 | $A351–$A50C | 0x0A351–0x0A50C | 0x00A361–0x00A51C | 444 |

## Address Conversion Reference

```
PRG offset from CPU address (switchable bank):
  prg_offset = bank * 0x4000 + (cpu_addr - 0x8000)

File offset (nes_open_us.nes, 16-byte iNES header, no trainer):
  file_offset = 0x10 + prg_offset
```
