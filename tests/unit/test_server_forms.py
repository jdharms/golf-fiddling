"""The generate form: submissions into settings, and the refusals it names."""

import pytest
from starlette.datastructures import FormData

from golf.core.patches.sram_defaults import Club
from golf.randomizer.catalog import JP_ROM, US_ROM
from golf.randomizer.manifest import DEFAULT_MERCY_POINT, ClubRules, Settings
from server.forms import (
    INVALID,
    MUSIC_CHOICES,
    NO_SOURCES,
    PARS,
    REQUIRED_BAG_BANNED,
    REQUIRED_BAG_OVER_MAX,
    RULE_CLUBS,
    FormError,
    FormState,
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
