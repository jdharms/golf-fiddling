"""
Multi-bank terrain distribution patches.

These patches enable per-hole bank lookup for terrain data, allowing
courses to span multiple banks instead of being limited to a single bank.

See docs/multi_bank_terrain.md for full details.
"""

from .byte_patch import BytePatch
from .composite import CompositePatch

# Code patch to change terrain bank lookup from course-based to hole-based.
#
# LoadTerrainAndAttrs ($DB5D) looks up the terrain bank by course number:
#   $DB68  LDX CurrCourse
#   $DB6B  LDA BankNumTerrainDataTable,X   ; 3 entries
#   $DB6E  JSR BankSwitchRoutine
#
# The first two instructions become a lookup by doubled hole index ($31) into
# the per-hole table at $A700 in bank 3, which is still switched in from
# DecompressGreen:
#   $DB68  LDX $31
#   $DB6A  LDA $A700,X
#   $DB6D  NOP
#
# The JSR at $DB6E is left in place, so ATTR_STREAMING_BANK_SWITCH_PATCH
# (attr_streaming.py) can redirect it independently of this patch.
MULTI_BANK_CODE_PATCH = BytePatch(
    name="multi_bank_lookup",
    description="Change terrain bank lookup from course-based to hole-based",
    prg_offset=0x3DB68,  # CPU $DB68 in fixed bank (bank 15)
    original=bytes([0xAE, 0x02, 0x01, 0xBD, 0xBE, 0xDB]),
    patched=bytes([0xA6, 0x31, 0xBD, 0x00, 0xA7, 0xEA]),
)

# Course 2 mirror patch - makes US (course 2) mirror Japan (course 1)
#
# This patches the CourseHoleOffsetTable at $DBBB which maps course indices
# to hole offsets: [0, 18, 36] -> [0, 0, 36]
#
# Used in 1-course mode so all three course slots show the same course.
COURSE2_MIRROR_PATCH = BytePatch(
    name="course2_mirror",
    description="Make course 2 (US) mirror course 1 (Japan)",
    prg_offset=0x3DBBC,  # CPU $DBBC in fixed bank (CourseHoleOffsetTable + 1)
    original=bytes([0x12]),
    patched=bytes([0x00]),
)

# Course 3 mirror patch - makes UK (course 3) mirror Japan (course 1)
#
# This patches the CourseHoleOffsetTable at $DBBB which maps course indices
# to hole offsets: [0, 18, 36] -> [0, 18, 0]
#
# When UK is selected, the game will use hole offset 0 (Japan's holes).
# This effectively reduces the game to 2 courses without UI changes,
# allowing the 3 terrain banks to be shared across 36 holes.
COURSE3_MIRROR_PATCH = BytePatch(
    name="course3_mirror",
    description="Make course 3 (UK) mirror course 1 (Japan)",
    prg_offset=0x3DBBD,  # CPU $DBBD in fixed bank (CourseHoleOffsetTable + 2)
    original=bytes([0x24]),
    patched=bytes([0x00]),
)

# Bank 2 contains its own private copy of the hole-offset table at CPU
# $B1F1-$B1F3, used by the scorecard's eagle/birdie/par/bogey face-drawing
# routine to index into the Par table ($DD05, fixed bank). This routine lives
# entirely in bank 2 and reads its local copy instead of the fixed-bank
# CourseHoleOffsetTable at $DBBB - the two tables hold identical values but
# are patched independently. Without these, the scorecard faces still use
# the original per-course offsets even after COURSE2/3_MIRROR_PATCH make the
# actual course data mirror course 1.
COURSE2_MIRROR_PATCH_SCORECARD = BytePatch(
    name="course2_mirror_scorecard",
    description="Make course 2 (US) mirror course 1 in the bank 2 scorecard face table",
    prg_offset=0xB1F2,  # CPU $B1F2 in bank 2 (scorecard hole-offset table + 1)
    original=bytes([0x12]),
    patched=bytes([0x00]),
)

COURSE3_MIRROR_PATCH_SCORECARD = BytePatch(
    name="course3_mirror_scorecard",
    description="Make course 3 (UK) mirror course 1 in the bank 2 scorecard face table",
    prg_offset=0xB1F3,  # CPU $B1F3 in bank 2 (scorecard hole-offset table + 2)
    original=bytes([0x24]),
    patched=bytes([0x00]),
)

# A ROM carries one course: every course slot plays holes 0-17, in both the
# fixed-bank offset table and the scorecard's bank 2 copy. Hole slots 18-53
# are never read.
COURSE_MIRRORS_PATCH = CompositePatch(
    name="course_mirrors",
    description="Make courses 2 (US) and 3 (UK) mirror course 1 (Japan)",
    patches=[
        COURSE2_MIRROR_PATCH,
        COURSE3_MIRROR_PATCH,
        COURSE2_MIRROR_PATCH_SCORECARD,
        COURSE3_MIRROR_PATCH_SCORECARD,
    ],
)

# All multi-bank patches in recommended application order
MULTI_BANK_PATCHES = [
    MULTI_BANK_CODE_PATCH,
    COURSE_MIRRORS_PATCH,
]
