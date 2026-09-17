"""The generate form: submissions into settings, and the refusals it names."""

import pytest
from starlette.datastructures import FormData

from golf.core.patches.sram_defaults import VANILLA_CLUBS, VANILLA_NAME, Club
from golf.randomizer.catalog import JP_ROM, US_ROM
from golf.randomizer.manifest import DEFAULT_MERCY_POINT, ClubRules, Settings
from golf.randomizer.roms import vanilla_rom
from server.forms import (
    CLUBS_BANNED,
    CLUBS_OVER_MAX,
    INVALID,
    INVALID_NAME,
    MUSIC_CHOICES,
    NO_SOURCES,
    PARS,
    REQUIRED_BAG_BANNED,
    REQUIRED_BAG_OVER_MAX,
    ROMS_MISSING,
    RULE_CLUBS,
    DownloadState,
    FormError,
    FormState,
    check_rom_hashes,
    player_options_from_state,
    settings_from_state,
)


def submit(**changes) -> Settings:
    return settings_from_state(state(**changes))


def state(**changes) -> FormState:
    form = FormState.default()
    for name, value in changes.items():
        setattr(form, name, value)
    return form


def refusal(**changes) -> FormError:
    with pytest.raises(FormError) as caught:
        submit(**changes)
    return caught.value


def test_the_default_form_submits_the_default_settings():
    settings = settings_from_state(FormState.from_form(FormData(FormState.default().to_pairs())))
    assert settings == Settings()


def test_the_form_lists_every_par_music_and_club_but_the_putter():
    assert PARS == (72, 71, 70)
    assert MUSIC_CHOICES[0] == "random" and len(MUSIC_CHOICES) == 9
    assert Club.PT not in RULE_CLUBS and len(RULE_CLUBS) == 15


def test_the_mercy_point_is_always_the_default_whatever_is_sent():
    form = FormData([*FormState.default().to_pairs(), ("mercy_point", "3")])
    assert settings_from_state(FormState.from_form(form)).mercy_point == DEFAULT_MERCY_POINT


def test_every_field_reaches_the_settings():
    settings = submit(
        par="70",
        sources={US_ROM},
        allow_family_repeats=True,
        music="jp_france",
        clubs_max="10",
        banned={"1W", "sw"},
        required_bag={"3W", "5I", "PW"},
    )
    assert settings == Settings(
        par=70,
        sources={US_ROM},
        allow_family_repeats=True,
        music="jp_france",
        clubs=ClubRules(
            max=10,
            banned={Club.W1, Club.SW},
            required_bag={Club.W3, Club.I5, Club.PW},
        ),
    )


def test_a_submission_round_trips_through_its_pairs():
    submitted = state(par="71", sources={JP_ROM}, allow_family_repeats=True, banned={"2I"}, required_bag={"1W"})
    assert FormState.from_form(FormData(submitted.to_pairs())) == submitted


def test_unknown_fields_and_blank_space_are_ignored():
    form = FormData([("par", " 72 "), ("sources", US_ROM), ("music", "random"), ("clubs_max", "14"), ("prng_seed", "x")])
    assert settings_from_state(FormState.from_form(form)) == Settings(sources={US_ROM})


def test_no_required_bag_checked_means_players_choose():
    assert submit(required_bag=set()).clubs.required_bag is None


def test_no_sources_is_refused():
    assert refusal(sources=set()).reason == NO_SOURCES


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"par": ""}, "par"),
        ({"par": "73"}, "par"),
        ({"sources": {US_ROM, "nes_open_jp"}}, "sources"),
        ({"music": "nes_mars"}, "music"),
        ({"music": ""}, "music"),
        ({"clubs_max": "0"}, "clubs_max"),
        ({"clubs_max": "15"}, "clubs_max"),
        ({"clubs_max": "ten"}, "clubs_max"),
        ({"banned": {"PT"}}, "banned"),
        ({"banned": {"9W"}}, "banned"),
        ({"required_bag": {"PT"}}, "required_bag"),
    ],
)
def test_values_the_form_cannot_send_are_refused_naming_the_field(changes, field):
    problem = refusal(**changes)
    assert problem.reason == INVALID
    assert problem.values == {"field": field}


def test_a_required_bag_over_the_max_is_refused_counting_the_putter():
    problem = refusal(clubs_max="3", required_bag={"1W", "3W", "PW"})
    assert problem.reason == REQUIRED_BAG_OVER_MAX
    assert problem.values == {"count": 4, "max": 3}
    assert submit(clubs_max="4", required_bag={"1W", "3W", "PW"}).clubs.max == 4


def test_a_required_bag_holding_banned_clubs_is_refused():
    problem = refusal(banned={"1W", "SW", "2I"}, required_bag={"SW", "1W", "PW"})
    assert problem.reason == REQUIRED_BAG_BANNED
    assert problem.values == {"clubs": "1W SW"}



# -- Download ---------------------------------------------------------------------------------

RULES = ClubRules()
US_SHA1 = vanilla_rom(US_ROM).sha1
JP_SHA1 = vanilla_rom(JP_ROM).sha1


def download(name: str = "luigi", clubs: set[str] | None = None, **hashes: str) -> DownloadState:
    return DownloadState(player_name=name, clubs={"1W", "PW"} if clubs is None else clubs, rom_hashes=hashes)


def download_refusal(state: DownloadState, rules: ClubRules = RULES) -> FormError:
    with pytest.raises(FormError) as caught:
        player_options_from_state(state, rules)
    return caught.value


def test_a_download_submission_reads_name_clubs_and_rom_hashes():
    form = FormData(
        [
            ("player_name", "  luigi "),
            ("clubs", "1W"),
            ("clubs", "PW"),
            ("rom_nes_open_us", US_SHA1.upper()),
            ("rom_mario_open_jp", JP_SHA1),
            ("other", "ignored"),
        ]
    )
    state = DownloadState.from_form(form)
    assert state == DownloadState("luigi", {"1W", "PW"}, {US_ROM: US_SHA1, JP_ROM: JP_SHA1})
    assert DownloadState.from_form(FormData(state.to_pairs())) == state


def test_the_download_default_is_the_vanilla_name_and_bag_without_banned_clubs():
    state = DownloadState.default(ClubRules(banned=frozenset({Club.W1})))
    assert state.player_name == VANILLA_NAME
    assert state.clubs == {club.label for club in VANILLA_CLUBS} - {"1W", "PT"}


def test_the_download_default_for_a_locked_bag_is_that_bag():
    rules = ClubRules(required_bag=frozenset({Club.W1, Club.PW}))
    assert DownloadState.default(rules).clubs == {"1W", "PW"}


def test_player_options_upper_case_the_name_and_add_the_putter():
    options = player_options_from_state(download("luigi"), RULES)
    assert options.player_name == "LUIGI"
    assert options.clubs == {Club.W1, Club.PW, Club.PT}
    assert options.bgm is True


def test_a_locked_bag_ignores_the_submitted_clubs():
    rules = ClubRules(required_bag=frozenset({Club.W3, Club.I5}))
    options = player_options_from_state(download(clubs={"1W", "2W", "9W"}), rules)
    assert options.clubs == {Club.W3, Club.I5, Club.PT}


@pytest.mark.parametrize(
    "name, chars",
    [("", ""), ("   ", ""), ("ABCDEFGHIJK", ""), ("L-U1GI", "-1"), ("MARIÖ", "Ö")],
)
def test_a_name_the_game_cannot_store_is_refused(name, chars):
    problem = download_refusal(download(name))
    assert problem.reason == INVALID_NAME
    assert problem.values == {"chars": chars}


def test_a_ten_character_name_with_dots_and_spaces_is_allowed():
    assert player_options_from_state(download("dr. mario."), RULES).player_name == "DR. MARIO."


def test_an_unknown_club_is_refused():
    problem = download_refusal(download(clubs={"1W", "9W"}))
    assert problem.reason == INVALID
    assert problem.values == {"field": "clubs"}


def test_a_bag_holding_banned_clubs_is_refused():
    rules = ClubRules(banned=frozenset({Club.W1, Club.SW}))
    problem = download_refusal(download(clubs={"SW", "1W", "PW"}), rules)
    assert problem.reason == CLUBS_BANNED
    assert problem.values == {"clubs": "1W SW"}


def test_a_bag_over_the_max_is_refused_counting_the_putter():
    problem = download_refusal(download(clubs={"1W", "3W", "PW"}), ClubRules(max=3))
    assert problem.reason == CLUBS_OVER_MAX
    assert problem.values == {"count": 4, "max": 3}


def test_rom_hashes_must_match_every_required_rom():
    check_rom_hashes(download(nes_open_us=US_SHA1, mario_open_jp=JP_SHA1), (US_ROM, JP_ROM))
    check_rom_hashes(download(nes_open_us=US_SHA1), (US_ROM,))


@pytest.mark.parametrize(
    "hashes, roms",
    [
        ({}, "NES Open Tournament Golf (USA), Mario Open Golf (Japan)"),
        ({"nes_open_us": US_SHA1}, "Mario Open Golf (Japan)"),
        ({"nes_open_us": US_SHA1, "mario_open_jp": US_SHA1}, "Mario Open Golf (Japan)"),
    ],
)
def test_a_missing_or_wrong_rom_hash_is_refused_naming_the_roms(hashes, roms):
    with pytest.raises(FormError) as caught:
        check_rom_hashes(download(**hashes), (US_ROM, JP_ROM))
    assert caught.value.reason == ROMS_MISSING
    assert caught.value.values == {"roms": roms}
