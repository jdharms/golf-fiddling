"""The site's app: health check, home, ROM setup, generate, the seed page, downloads and static files."""

import re

import pytest
from fastapi.testclient import TestClient

from golf.core.patches.sram_defaults import Club
from golf.randomizer.catalog import JP_ROM, US_ROM, Catalog, HoleStore
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.generate import GenerationError
from golf.randomizer.manifest import DEFAULT_MERCY_POINT, Manifest
from golf.randomizer.roms import VANILLA_ROMS, vanilla_rom
from server.app import create_app
from server.builder import SeedBuilder
from server.config import Config
from server.forms import FormState
from server.migrations import MIGRATIONS
from server.ratelimit import RateLimiter
from server.strings import Entry, Strings

IPS = b"PATCH\x00\x00\x10\x00\x01\xeaEOF"
FINISHED = b"PATCH\x00\x00\x20\x00\x01\x60EOF"
SEED_URL = re.compile(r"^/h/([0-9A-Za-z]{10})$")


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture(scope="module")
def curation() -> CurationSnapshot:
    return CurationSnapshot.load()


class FakeBuilder(SeedBuilder):
    """Generates for real and stores a fixed IPS instead of building, so no ROM is needed."""

    def build(self, manifest):
        self.built = manifest
        return IPS

    def finish(self, manifest, unfinished_ips, options):
        self.finished = (manifest, unfinished_ips, options)
        return FINISHED


class PoolTooSmall(FakeBuilder):
    def generate(self, settings):
        raise GenerationError("no fill")


@pytest.fixture
def fake_builder(catalog, curation, tmp_path):
    return FakeBuilder(catalog, curation, HoleStore(), tmp_path / "unused.nes")


def app_client(**kwargs) -> TestClient:
    return TestClient(create_app(Config(database=":memory:"), **kwargs))


@pytest.fixture
def client(fake_builder):
    with app_client(builder=fake_builder) as test_client:
        yield test_client


def _catalog_with_text(text_for) -> Strings:
    real = Strings.load()
    return Strings({key: Entry(real.entry(key).note, text_for(key)) for key in real.keys()})  # noqa: SIM118 (Strings, not a dict)


#: nothing written, so every string renders as the placeholder naming its key and values
UNWRITTEN = _catalog_with_text(lambda key: "")


@pytest.fixture
def unwritten_client(fake_builder):
    """For tests that name the notice a page shows by its key rather than by what it says."""
    with app_client(strings=UNWRITTEN, builder=fake_builder) as test_client:
        yield test_client


def form_data(form: FormState | None = None) -> dict[str, list[str]]:
    data: dict[str, list[str]] = {}
    for name, value in (form or FormState.default()).to_pairs():
        data.setdefault(name, []).append(value)
    return data


def post_generate(client: TestClient, form: FormState | None = None, **headers):
    return client.post("/generate", data=form_data(form), headers=headers, follow_redirects=False)


def generate_seed(client: TestClient, form: FormState | None = None) -> str:
    response = post_generate(client, form)
    assert response.status_code == 303, response.text
    return SEED_URL.match(response.headers["location"]).group(1)


def seed_count(client: TestClient) -> int:
    with client.app.state.db.transaction() as conn:
        return conn.execute("SELECT count(*) FROM seeds").fetchone()[0]


def test_health_check(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_migrates_the_database(client):
    assert client.app.state.db.version() == len(MIGRATIONS)


def test_startup_makes_a_builder_from_the_config_when_given_none(tmp_path):
    with TestClient(create_app(Config(database=":memory:", rom_dir=tmp_path))) as test_client:
        assert test_client.app.state.builder.rom_path == tmp_path / "nes_open_us.nes"


def test_home_links_to_rom_setup_and_generate(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'href="/rom"' in response.text
    assert 'href="/generate"' in response.text


def test_rom_setup_lists_every_vanilla_rom_with_its_hash(client):
    response = client.get("/rom")
    assert response.status_code == 200
    for rom in VANILLA_ROMS:
        assert f'data-rom-id="{rom.id}"' in response.text
        assert f'data-sha1="{rom.sha1}"' in response.text
        assert rom.title in response.text
    assert response.text.count('data-state="checking"') == len(VANILLA_ROMS)
    assert 'id="rom-strings"' in response.text
    assert response.text.index('src="/static/romstore.js"') < response.text.index('src="/static/rom.js"')


@pytest.mark.parametrize(
    "path",
    ["/static/pico.green.min.css", "/static/site.css", "/static/romstore.js", "/static/rom.js", "/static/download.js"],
)
def test_static_files_are_served(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.content


def test_pages_use_the_vendored_and_site_stylesheets(client):
    page = client.get("/").text
    assert 'href="/static/pico.green.min.css"' in page
    assert 'href="/static/site.css"' in page


def test_api_docs_are_not_exposed(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


# -- Generate ---------------------------------------------------------------------------------


def test_the_generate_form_offers_every_setting_with_its_default(client):
    response = client.get("/generate")
    assert response.status_code == 200
    page = response.text
    assert 'aria-current="page"' in page and 'href="/generate" ' in page
    assert len(re.findall(r'name="par"', page)) == 3
    assert re.search(r'name="par" value="72"\s+checked', page)
    for rom in VANILLA_ROMS:
        assert re.search(rf'name="sources" value="{rom.id}"\s+checked', page)
    assert 'name="allow_family_repeats"' in page
    assert re.search(r'<option value="random"\s+selected', page)
    assert page.count("<option ") == 9
    assert re.search(r'name="clubs_max"[^>]*value="14"', page)
    assert page.count('name="banned"') == 15
    assert page.count('name="required_bag"') == 15
    assert 'value="PT"' not in page
    assert "mercy" not in page


def test_club_rules_are_a_section_of_their_own_after_the_everyday_settings(client):
    page = client.get("/generate").text
    rules = page.index('<article class="club-rules">')
    assert page.index('name="music"') < rules < page.index('name="clubs_max"')
    assert page.index('name="required_bag"') < page.index("</article>", rules) < page.index('type="submit"')


def test_generating_stores_the_seed_and_redirects_to_its_page(client, fake_builder):
    seed_id = generate_seed(client)
    with client.app.state.db.transaction() as conn:
        seed = conn.execute("SELECT * FROM seeds WHERE id = ?", (seed_id,)).fetchone()
        holes = conn.execute("SELECT count(*) FROM seed_holes WHERE seed_id = ?", (seed_id,)).fetchone()[0]
    assert seed["unfinished_ips"] == IPS
    assert holes == 18
    stored = Manifest.from_json(__import__("json").loads(seed["manifest"]))
    assert stored == fake_builder.built
    assert stored.settings.mercy_point == DEFAULT_MERCY_POINT


def test_the_seed_page_shows_the_course(client, fake_builder, catalog):
    seed_id = generate_seed(client)
    manifest = fake_builder.built
    response = client.get(f"/h/{seed_id}")
    assert response.status_code == 200
    page = response.text
    assert " ".join(manifest.course.magic_words) in page
    codes = re.findall(r"<code>([^<]+)</code>", page)
    assert codes == [str(slot.id) for slot in manifest.course.holes]
    yards = sum(catalog[slot.id].distance for slot in manifest.course.holes)
    assert f'<td class="num">{manifest.course.par}</td>' in page
    assert f'<td class="num">{yards}</td>' in page
    assert f'href="/h/{seed_id}.json"' in page
    assert "Mario Open Golf (Japan)" in page or "NES Open Tournament Golf (USA)" in page


def test_the_manifest_json_is_the_stored_manifest(client, fake_builder):
    seed_id = generate_seed(client)
    response = client.get(f"/h/{seed_id}.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert Manifest.from_json(response.json()) == fake_builder.built
    with client.app.state.db.transaction() as conn:
        assert response.text == conn.execute("SELECT manifest FROM seeds").fetchone()[0]


@pytest.mark.parametrize("path", ["/h/0000000001", "/h/not-a-seed", "/h/0000000000", "/no-such-page"])
def test_unknown_pages_render_not_found(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "not_found.heading" in response.text or "<h1>" in response.text


@pytest.mark.parametrize("path", ["/h/0000000001.json", "/h/nope.json"])
def test_unknown_manifests_are_json_404s(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_a_refused_form_comes_back_with_its_values_and_a_notice(unwritten_client):
    form = FormState.default()
    form.par = "70"
    form.sources = set()
    form.banned = {"2W"}
    response = post_generate(unwritten_client, form)
    assert response.status_code == 400
    page = response.text
    assert 'role="alert"' in page and "generate.error.no_sources" in page
    assert re.search(r'name="par" value="70"\s+checked', page)
    assert re.search(r'name="banned" value="2W"\s+checked', page)
    assert seed_count(unwritten_client) == 0


def test_a_club_rule_refusal_names_its_values(unwritten_client):
    form = FormState.default()
    form.clubs_max = "2"
    form.required_bag = {"1W", "PW"}
    response = post_generate(unwritten_client, form)
    assert response.status_code == 400
    assert "generate.error.required_bag_over_max count=3 max=2" in response.text


def test_a_pool_that_cannot_fill_the_course_is_refused(catalog, curation, tmp_path):
    with app_client(strings=UNWRITTEN, builder=PoolTooSmall(catalog, curation, HoleStore(), tmp_path / "x.nes")) as test_client:
        response = post_generate(test_client)
        assert response.status_code == 400
        assert "generate.error.pool" in response.text
        assert seed_count(test_client) == 0


def test_generating_is_rate_limited_per_client(fake_builder):
    with app_client(strings=UNWRITTEN, builder=fake_builder, rate_limiter=RateLimiter(1, 3600)) as test_client:
        assert post_generate(test_client, **{"X-Forwarded-For": "192.0.2.1"}).status_code == 303
        refused = post_generate(test_client, **{"X-Forwarded-For": "192.0.2.1"})
        assert refused.status_code == 429
        assert "generate.error.rate_limited" in refused.text
        assert post_generate(test_client, **{"X-Forwarded-For": "192.0.2.2"}).status_code == 303
        assert seed_count(test_client) == 2


def test_a_refused_form_spends_no_token(fake_builder):
    invalid = FormState.default()
    invalid.sources = set()
    with app_client(builder=fake_builder, rate_limiter=RateLimiter(1, 3600)) as test_client:
        assert post_generate(test_client, invalid).status_code == 400
        assert post_generate(test_client).status_code == 303


def test_generating_without_the_servers_rom_is_unavailable(catalog, curation, tmp_path):
    missing = SeedBuilder(catalog, curation, HoleStore(), tmp_path / "missing.nes")
    with app_client(strings=UNWRITTEN, builder=missing) as test_client:
        response = post_generate(test_client)
        assert response.status_code == 503
        assert "generate.error.unavailable" in response.text
        assert seed_count(test_client) == 0


# -- Download ---------------------------------------------------------------------------------

US_HASHES = {f"rom_{US_ROM}": vanilla_rom(US_ROM).sha1}
ALL_HASHES = {f"rom_{rom.id}": rom.sha1 for rom in VANILLA_ROMS}


def seed_form(**changes) -> FormState:
    form = FormState.default()
    for name, value in changes.items():
        setattr(form, name, value)
    return form


#: a seed built from the US ROM alone: its holes and its theme
US_ONLY = {"sources": {US_ROM}, "music": "nes_us"}


def post_download(client: TestClient, seed_id: str, name: str = "luigi", clubs=("1W", "PW"), hashes=None):
    data = {"player_name": name, "clubs": list(clubs), **(ALL_HASHES if hashes is None else hashes)}
    return client.post(f"/h/{seed_id}/patch.ips", data=data)


def test_the_seed_page_offers_the_download_form(client):
    seed_id = generate_seed(client, seed_form(**US_ONLY, banned={"1W", "SW"}))
    page = client.get(f"/h/{seed_id}").text
    article = page[page.index('<article class="download"') : page.index("</article>", page.index('<article class="download"'))]
    assert 'data-state="checking"' in article
    assert f'data-required-roms="{US_ROM}"' in article
    assert f'data-filename="notgr_par72_{seed_id}.nes"' in article
    assert f'action="/h/{seed_id}/patch.ips"' in article
    assert re.search(r'name="player_name" value="MARIO"\s+maxlength="10"', article)
    assert article.count('name="clubs"') == 15
    assert 'value="PT"' not in article
    assert re.search(r'name="clubs" value="1W" disabled', article)
    assert re.search(r'name="clubs" value="SW" disabled', article)
    assert re.search(r'name="clubs" value="3W" checked', article)
    assert not re.search(r'name="clubs" value="4W" checked', article)
    assert re.search(r'<button type="submit" disabled>', article)
    assert 'href="/rom"' in article
    assert 'id="download-strings"' in page
    assert f'id="download-roms">{{"{US_ROM}": {{"sha1": "{vanilla_rom(US_ROM).sha1}"' in page
    assert page.index('src="/static/romstore.js"') < page.index('src="/static/download.js"')


def test_a_locked_bag_seed_lists_no_clubs(unwritten_client):
    seed_id = generate_seed(unwritten_client, seed_form(required_bag={"1W", "PW"}))
    page = unwritten_client.get(f"/h/{seed_id}").text
    assert 'name="clubs"' not in page
    assert "seed.download.locked_bag clubs=1W PW PT" in page


def test_downloading_finishes_the_stored_seed_as_a_guest(client, fake_builder):
    seed_id = generate_seed(client)
    response = post_download(client, seed_id)
    assert response.status_code == 200
    assert response.content == FINISHED
    assert response.headers["content-type"] == "application/octet-stream"
    par = fake_builder.built.course.par
    assert response.headers["content-disposition"] == f'attachment; filename="notgr_par{par}_{seed_id}.ips"'
    manifest, unfinished_ips, options = fake_builder.finished
    assert manifest == fake_builder.built
    assert unfinished_ips == IPS
    assert options.player_name == "LUIGI"
    assert options.clubs == {Club.W1, Club.PW, Club.PT}


def test_a_us_only_seed_needs_only_the_us_hash(client):
    seed_id = generate_seed(client, seed_form(**US_ONLY))
    assert post_download(client, seed_id, hashes=US_HASHES).status_code == 200


def test_a_seed_with_mario_open_content_is_refused_without_the_jp_hash(client):
    seed_id = generate_seed(client, seed_form(music="jp_france"))
    response = post_download(client, seed_id, hashes=US_HASHES)
    assert response.status_code == 403
    assert response.json() == {"error": "roms_missing", "values": {"roms": vanilla_rom(JP_ROM).title}}


def test_a_download_without_hashes_is_refused(client):
    seed_id = generate_seed(client, seed_form(**US_ONLY))
    response = post_download(client, seed_id, hashes={})
    assert response.status_code == 403
    assert response.json()["error"] == "roms_missing"


@pytest.mark.parametrize(
    "form, name, clubs, error",
    [
        ({}, "LU1GI", ("1W",), {"error": "invalid_name", "values": {"chars": "1"}}),
        ({}, "", ("1W",), {"error": "invalid_name", "values": {"chars": ""}}),
        ({}, "LUIGI", ("9W",), {"error": "invalid", "values": {"field": "clubs"}}),
        ({"banned": {"SW"}}, "LUIGI", ("SW", "PW"), {"error": "clubs_banned", "values": {"clubs": "SW"}}),
        ({"clubs_max": "2"}, "LUIGI", ("1W", "PW"), {"error": "clubs_over_max", "values": {"count": 3, "max": 2}}),
    ],
)
def test_a_download_the_seed_forbids_is_refused(client, form, name, clubs, error):
    seed_id = generate_seed(client, seed_form(**form))
    response = post_download(client, seed_id, name=name, clubs=clubs)
    assert response.status_code == 400
    assert response.json() == error


def test_downloading_an_unknown_seed_is_a_json_404(client):
    for seed_id in ("0000000001", "not-a-seed"):
        response = post_download(client, seed_id)
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}


def test_downloading_without_the_servers_rom_is_unavailable(catalog, curation, tmp_path):
    class NoRom(SeedBuilder):
        def build(self, manifest):
            return IPS

    with app_client(builder=NoRom(catalog, curation, HoleStore(), tmp_path / "missing.nes")) as test_client:
        seed_id = generate_seed(test_client)
        response = post_download(test_client, seed_id)
        assert response.status_code == 503
        assert response.json() == {"error": "unavailable", "values": {}}


# -- Strings ----------------------------------------------------------------------------------


def test_written_strings_render_without_placeholders(fake_builder):
    written = _catalog_with_text(lambda key: f"TEXT:{key}")
    with app_client(strings=written, builder=fake_builder) as test_client:
        seed_id = generate_seed(test_client)
        pages = {path: test_client.get(path).text for path in ("/", "/rom", "/generate", f"/h/{seed_id}", "/nope")}
    for page in pages.values():
        assert "⟦" not in page
        assert 'class="unwritten"' not in page
    assert "TEXT:home.heading" in pages["/"]
    assert "<title>TEXT:rom.page_title</title>" in pages["/rom"]
    assert '"TEXT:rom.status.stored"' in pages["/rom"]
    assert "TEXT:generate.clubs.heading" in pages["/generate"]
    assert "TEXT:seed.holes.total" in pages[f"/h/{seed_id}"]
    assert "TEXT:seed.download.submit" in pages[f"/h/{seed_id}"]
    assert '"TEXT:seed.download.status.ready"' in pages[f"/h/{seed_id}"]
    assert "TEXT:not_found.heading" in pages["/nope"]


def test_unwritten_strings_render_as_placeholders_with_their_notes(fake_builder):
    unwritten = _catalog_with_text(lambda key: "")
    with app_client(strings=unwritten, builder=fake_builder) as test_client:
        rom = test_client.get("/rom").text
    assert "<title>⟦rom.page_title⟧</title>" in rom
    assert '<span class="unwritten" title="ROM setup page h1">⟦rom.heading⟧</span>' in rom
    assert f"⟦rom.expected_hash sha1={VANILLA_ROMS[0].sha1}⟧" in rom
    assert '"rom.status.stored": null' in rom
