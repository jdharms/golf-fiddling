"""
Remove-the-course-banner patch for the pre-hole signpost.

For a randomizer that shuffles holes between courses (see docs/randomizer.md),
`LC_AC2F_DrawSignpostCard`'s "JAPAN COURSE"/"US COURSE"/"UK COURSE" banner
(bank 12, docs/prehole_signpost.md) becomes actively misleading - the country
name no longer says anything true about a mixed-hole course. This patch drops
the whole banner and the one decorative object that connects it to the
remaining HOLE/PAR/yards signs.

Two independent things get patched:

1. **Skip the banner draw.** `LC_AC2F_DrawSignpostCard`'s course/contest index
   selection and the `WriteNametableTiles` call it feeds (`$AC5D`-`$AC83`, 39
   bytes) - nothing else jumps into mid-block (confirmed with `find-refs` on
   the two internal loop labels, `LC_AC69`/`LC_AC75` - both are only reached
   from inside this same span), so a same-length 3-byte redirect at the top
   is enough:

     original: AE 02 01           (LDX CurrCourse)
     patched:  4C 84 AC           (JMP $AC84, the hole-number section)

   `$AC84`-on is untouched, so hole number/par/yardage still draw normally.

2. **Drop the one connecting object, not two.** `$AC50`'s `LDA #$04 : JSR
   AllocateObjectRecords : .dw $B070` places 4 decorative objects at Y
   `$4F`/`$67`/`$7F`/`$97` (bank 12, `$B070`-`$B093`, 9 bytes each) - evenly
   spaced 24px apart, matching the 24px gap between the HOLE/PAR/yards lines.
   Playtesting (jdharms, emulator) showed these are the chain/post links
   *between* consecutive signs (banner-to-HOLE, HOLE-to-PAR, PAR-to-yards,
   yards-to-ground), not a left/right pair holding up any one sign - an
   earlier version of this patch dropped records 1 and 2 on the theory that
   two sprites held up the banner together, which removed the wrong (and
   wrong number of) links. Only the topmost one, record 0 (`$4F`, the
   smallest Y = highest on screen - the banner-to-HOLE link) needs to go once
   the banner above it is gone; the other three still connect the signs that
   remain. `AllocateObjectRecords` reads `count` 9-byte records sequentially
   from the pointer, so dropping record 0 alone is just: read 3 records
   starting one record later.

     count byte at $AC51:  04 -> 03
     pointer at $AC55-56:  B070 -> B079   (skip record 0 entirely)

Neither change touches CHR or the `$D4C3`-compressed graphics tables, and
neither needs new free space or any data rewriting - both are in-place,
same-length edits to the call site only.
"""

from .byte_patch import BytePatch
from .composite import CompositePatch

_SKIP_DRAW_PRG_OFFSET = 0x32C5D  # CPU $AC5D, bank 12 (LDX CurrCourse)
_SKIP_DRAW_ORIGINAL = bytes([0xAE, 0x02, 0x01])
_SKIP_DRAW_PATCHED = bytes([0x4C, 0x84, 0xAC])  # JMP $AC84

_OBJECT_COUNT_PRG_OFFSET = 0x32C51  # CPU $AC51, bank 12 (LDA #$04's operand)
_OBJECT_COUNT_ORIGINAL = bytes([0x04])
_OBJECT_COUNT_PATCHED = bytes([0x03])

_OBJECT_PTR_PRG_OFFSET = 0x32C55  # CPU $AC55-56, bank 12 (AllocateObjectRecords' inline pointer)
_OBJECT_PTR_ORIGINAL = bytes([0x70, 0xB0])  # $B070 (record 0, the banner-to-HOLE link)
_OBJECT_PTR_PATCHED = bytes([0x79, 0xB0])  # $B079 (record 1: HOLE-to-PAR link, now first)


def remove_course_banner_patches() -> CompositePatch:
    """Skip drawing the country-name banner and the object linking it to HOLE."""
    skip_draw_patch = BytePatch(
        name="signpost_skip_banner_draw",
        description=(
            "Redirect LC_AC2F_DrawSignpostCard past the course/contest banner "
            "selection and draw, straight to the hole-number section"
        ),
        prg_offset=_SKIP_DRAW_PRG_OFFSET,
        original=_SKIP_DRAW_ORIGINAL,
        patched=_SKIP_DRAW_PATCHED,
    )

    object_count_patch = BytePatch(
        name="signpost_reduce_banner_object_count",
        description="AllocateObjectRecords count for the sign-chain objects: 4 -> 3",
        prg_offset=_OBJECT_COUNT_PRG_OFFSET,
        original=_OBJECT_COUNT_ORIGINAL,
        patched=_OBJECT_COUNT_PATCHED,
    )

    object_ptr_patch = BytePatch(
        name="signpost_skip_banner_link_object",
        description=(
            "Advance AllocateObjectRecords' source pointer past record 0 "
            "(the banner-to-HOLE chain link), keeping records 1-3"
        ),
        prg_offset=_OBJECT_PTR_PRG_OFFSET,
        original=_OBJECT_PTR_ORIGINAL,
        patched=_OBJECT_PTR_PATCHED,
    )

    return CompositePatch(
        name="remove_course_banner",
        description="Drop the JAPAN/US/UK COURSE banner text and its connecting chain link",
        patches=[skip_draw_patch, object_count_patch, object_ptr_patch],
    )
