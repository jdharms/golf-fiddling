"""
Multi-bank terrain distribution patches.

These patches enable per-hole bank lookup for terrain data, allowing
courses to span multiple banks instead of being limited to a single bank.

See docs/multi_bank_terrain.md for full details.
"""

from .byte_patch import BytePatch

# Original code at $DB68 looks up bank by course number (3 entries):
#   LDX CourseNumber; LDA BankNumTerrainDataTable,X; JSR BankSwitchRoutine
_MULTI_BANK_ORIGINAL = bytes([0xAE, 0x02, 0x01, 0xBD, 0xBE, 0xDB, 0x20, 0x52, 0xD3])

# Code patch to change terrain bank lookup from course-based to hole-based
#
# Patched code uses doubled hole index ($31) to look up per-hole table at $A700:
#   LDX $31; LDA $A700,X; JSR BankSwitchRoutine; NOP
#
# This enables 54 per-hole bank entries instead of 3 per-course entries.
MULTI_BANK_CODE_PATCH = BytePatch(
    name="multi_bank_lookup",
    description="Change terrain bank lookup from course-based to hole-based",
    prg_offset=0x3DB68,  # CPU $DB68 in fixed bank (bank 15)
    original=_MULTI_BANK_ORIGINAL,
    patched=bytes([0xA6, 0x31, 0xBD, 0x00, 0xA7, 0x20, 0x52, 0xD3, 0xEA]),
)

# Same hole-based bank lookup as MULTI_BANK_CODE_PATCH, but for use together
# with the attr_streaming patch set (see patches/attr_streaming.py).
#
# MULTI_BANK_CODE_PATCH's replacement shrinks the LDX+LDA sequence from 6
# bytes to 5, which shifts the JSR BankSwitchRoutine call one byte earlier
# (from $DB6E to $DB6D) - right through the middle of the JSR that
# attr_streaming's LoadTerrainAndAttrs patch expects to find, byte-for-byte,
# at $DB6E. Applying both patches to the same ROM is a genuine conflict:
# whichever applies second won't find its expected original bytes.
#
# Since a JSR is 3 bytes regardless of target, the fix is to redirect that
# already-shifted JSR to attr_streaming's SaveBankAndSwitch trampoline
# ($E1BE) instead of BankSwitchRoutine ($D352) directly - same bank-switch
# behavior, plus the AttrDataBank bookkeeping attr_streaming needs. This
# patch IS that redirect; use it in place of MULTI_BANK_CODE_PATCH whenever
# attr_streaming is also applied, never both at once.
MULTI_BANK_CODE_PATCH_WITH_ATTR_STREAMING = BytePatch(
    name="multi_bank_lookup_attr_streaming",
    description=(
        "Change terrain bank lookup from course-based to hole-based, "
        "redirected through SaveBankAndSwitch for attr streaming"
    ),
    prg_offset=0x3DB68,  # CPU $DB68 in fixed bank (bank 15)
    original=_MULTI_BANK_ORIGINAL,
    patched=bytes([0xA6, 0x31, 0xBD, 0x00, 0xA7, 0x20, 0xBE, 0xE1, 0xEA]),
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

# All multi-bank patches in recommended application order
MULTI_BANK_PATCHES = [
    MULTI_BANK_CODE_PATCH,
    COURSE3_MIRROR_PATCH,
]
