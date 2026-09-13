# Documentation Index

One line per document. Command-line tools are indexed in the top-level `README.md`.

## Plans and design

| Doc | About |
|-----|-------|
| [randomizer.md](randomizer.md) | Randomizer design: goals, logic, what gets randomized |
| [jp_extraction.md](jp_extraction.md) | Extracting Mario Open Golf (JP) courses for import into the US ROM |

## How the vanilla ROM works

| Doc | About |
|-----|-------|
| [../golf/core/compression.md](../golf/core/compression.md) | Course terrain/greens compression: RLE + dictionary, horizontal transitions, vertical fill |
| [terrain_data_locations.md](terrain_data_locations.md) | Byte ranges of the three vanilla courses' compressed terrain |
| [course_data.md](course_data.md) | The hole data model and JSON format the tools and editor share |
| [menu_system.md](menu_system.md) | The data-driven title-screen menu chain |
| [course_intro_scene.md](course_intro_scene.md) | The full-screen landscape shown after picking a course |
| [golfer_sprites.md](golfer_sprites.md) | How the swinging golfer and club are drawn |
| [scorecard.md](scorecard.md) | The pause-menu scorecard screen |
| [prize_money.md](prize_money.md) | The PRIZE MONEY clubhouse cutscene |
| [hud_course_abbrev.md](hud_course_abbrev.md) | The course abbreviation in the in-game HUD |
| [music_format.md](music_format.md) | The audio engine and track format, including inserting tracks |
| [curiosity.md](curiosity.md) | Parked side findings, not yet investigated |

## Patches

| Doc | About |
|-----|-------|
| [patch_stack.md](patch_stack.md) | Building a ROM from an ordered stack of patches, and IPS output |
| [multi_bank_terrain.md](multi_bank_terrain.md) | Writing a course across terrain banks 0 and 1 (`golf-write`) |
| [wram_expansion.md](wram_expansion.md) | Growing the terrain buffer past 48 rows |
| [seeded_wind.md](seeded_wind.md) | Pin positions and wind as a function of a build-time seed |
| [practice_swing.md](practice_swing.md) | Practice swings that cost no stroke |
| [putting_practice.md](putting_practice.md) | Starting every hole as a putt (design note, not shipped) |
| [prehole_signpost.md](prehole_signpost.md) | The pre-hole signpost card, and replacing its banner art |
| [scorecard_qr.md](scorecard_qr.md) | End-of-round QR code submission, and its 6502 port |
| [scorecard_qr_mask_sweep.md](scorecard_qr_mask_sweep.md) | Results of the QR mask/capture-condition validation sweep |

## Guides

| Doc | About |
|-----|-------|
| [composing.md](composing.md) | Writing music for the game, for a composer |

## Editor

| Doc | About |
|-----|-------|
| [../editor/CLAUDE.md](../editor/CLAUDE.md) | Editor architecture and how to add editor tools |
| [forest_notes.md](forest_notes.md) | The forest fill algorithm |
