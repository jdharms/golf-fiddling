"""The site's app: health check, home, ROM setup, generate, the seed page, downloads and static files."""

import re
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from golf.core.patches.sram_defaults import Club
from golf.qr.payload import URL_PREFIX, HoleRecord, RoundPayload
from golf.randomizer.catalog import JP_ROM, US_ROM, Catalog, HoleStore
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.generate import GenerationError
from golf.randomizer.manifest import DEFAULT_MERCY_POINT, Manifest
from golf.randomizer.roms import VANILLA_ROMS, vanilla_rom
from server.app import SESSION_COOKIE, create_app
from server.auth import DiscordClient, DiscordError, DiscordIdentity
from server.builder import SeedBuilder
from server.config import Config, ConfigError
from server.forms import FormState
from server.migrations import MIGRATIONS
from server.pages import PageCatalog
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

    def finish(self, manifest, unfinished_ips, options, credentials=None):
        self.finished = (manifest, unfinished_ips, options)
        self.credentials = credentials
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
    keys = real.keys()
    return Strings({key: Entry(real.entry(key).note, text_for(key)) for key in keys})


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
    return client.post(
        "/generate", data=form_data(form), headers=headers, follow_redirects=False
    )


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
    with TestClient(
        create_app(Config(database=":memory:", rom_dir=tmp_path))
    ) as test_client:
        assert test_client.app.state.builder.rom_path == tmp_path / "nes_open_us.nes"


def test_home_links_to_rom_setup_and_generate(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'href="/rom"' in response.text
    assert 'href="/generate"' in response.text
    assert 'href="/rangefinder"' in response.text
    assert "nav.pages" not in response.text


def test_rangefinder_page_embeds_its_assets_and_script_strings(unwritten_client):
    response = unwritten_client.get("/rangefinder")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert re.search(r'href="/rangefinder"\s+aria-current="page"', response.text)
    assert 'data-metadata-url="/static/rangefinder/metadata.json"' in response.text
    assert 'src="/static/rangefinder/app.js"' in response.text
    assert '"rangefinder.script.distance": null' in response.text


def test_rangefinder_generated_assets_are_served(client):
    metadata = client.get("/static/rangefinder/metadata.json")
    image = client.get("/static/rangefinder/images/japan/hole_01.png")
    assert metadata.status_code == 200
    assert metadata.json()["courses"]["japan"]["holes"][0]["width"] == 176
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"


def write_content_page(
    tmp_path, slug: str, metadata: str, body: str = "Page body."
) -> None:
    (tmp_path / f"{slug}.md").write_text(f"+++\n{metadata}\n+++\n\n{body}\n")


def page_catalog(tmp_path, metadata: str, body: str = "Page body.") -> PageCatalog:
    write_content_page(tmp_path, "review-page", metadata, body)
    return PageCatalog.load(tmp_path)


def test_navigation_lists_only_enabled_listed_pages_in_display_order(
    fake_builder, tmp_path
):
    write_content_page(
        tmp_path, "later", 'title = "Later"\nnav_title = "Zed"\norder = 20'
    )
    write_content_page(
        tmp_path, "first", 'title = "First"\nnav_title = "A & B"\norder = 10'
    )
    write_content_page(tmp_path, "review", 'title = "Review"\nlisted = false')
    write_content_page(
        tmp_path, "disabled", 'title = "Disabled"\nenabled = false\nlisted = false'
    )
    pages = PageCatalog.load(tmp_path)
    with app_client(
        builder=fake_builder, pages=pages, strings=UNWRITTEN
    ) as test_client:
        response = test_client.get("/")
    assert response.status_code == 200
    assert "⟦nav.pages⟧" in response.text
    assert response.text.index('href="/pages/first"') < response.text.index(
        'href="/pages/later"'
    )
    assert ">A &amp; B</a>" in response.text
    assert 'href="/pages/review"' not in response.text
    assert 'href="/pages/disabled"' not in response.text


def test_content_page_marks_its_dropdown_and_link_current(fake_builder, tmp_path):
    pages = page_catalog(tmp_path, 'title = "Review"')
    with app_client(builder=fake_builder, pages=pages) as test_client:
        response = test_client.get("/pages/review-page")
    assert response.status_code == 200
    assert '<summary aria-current="page">' in response.text
    assert re.search(
        r'<a href="/pages/review-page"\s+aria-current="page">Review</a>', response.text
    )


def test_markdown_page_is_served_with_its_title_and_body(fake_builder, tmp_path):
    pages = page_catalog(
        tmp_path, 'title = "Review & Notes"', "A **rendered** paragraph."
    )
    with app_client(builder=fake_builder, pages=pages) as test_client:
        response = test_client.get("/pages/review-page")
    assert response.status_code == 200
    assert "<title>Review &amp; Notes — NES Open Randomizer</title>" in response.text
    assert "<h1>Review &amp; Notes</h1>" in response.text
    assert "<p>A <strong>rendered</strong> paragraph.</p>" in response.text
    assert 'name="robots"' not in response.text


def test_unlisted_markdown_page_is_served_with_noindex(fake_builder, tmp_path):
    pages = page_catalog(tmp_path, 'title = "Review"\nlisted = false')
    with app_client(builder=fake_builder, pages=pages) as test_client:
        response = test_client.get("/pages/review-page")
    assert response.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in response.text
    assert 'href="/pages/review-page"' not in response.text


def test_disabled_and_unknown_markdown_pages_are_not_found(fake_builder, tmp_path):
    pages = page_catalog(
        tmp_path, 'title = "Disabled"\nenabled = false\nlisted = false'
    )
    with app_client(builder=fake_builder, pages=pages) as test_client:
        disabled = test_client.get("/pages/review-page")
        unknown = test_client.get("/pages/missing")
    assert disabled.status_code == 404
    assert unknown.status_code == 404
    assert "Disabled" not in disabled.text


def test_rom_setup_lists_every_vanilla_rom_with_its_hash(client):
    response = client.get("/rom")
    assert response.status_code == 200
    for rom in VANILLA_ROMS:
        assert f'data-rom-id="{rom.id}"' in response.text
        assert f'data-sha1="{rom.sha1}"' in response.text
        assert rom.title in response.text
    assert response.text.count('data-state="checking"') == len(VANILLA_ROMS)
    assert 'id="rom-strings"' in response.text
    assert response.text.index('src="/static/romstore.js"') < response.text.index(
        'src="/static/rom.js"'
    )


@pytest.mark.parametrize(
    "path",
    [
        "/static/pico.green.min.css",
        "/static/site.css",
        "/static/romstore.js",
        "/static/rom.js",
        "/static/download.js",
    ],
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
    assert re.search(r'href="/generate"\s+aria-current="page"', page)
    assert len(re.findall(r'name="par"', page)) == 3
    assert re.search(r'name="par"\s+value="72"\s+checked', page)
    for rom in VANILLA_ROMS:
        assert re.search(rf'name="sources"\s+value="{rom.id}"\s+checked', page)
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
    assert (
        page.index('name="required_bag"')
        < page.index("</article>", rules)
        < page.index('type="submit"')
    )


def test_generating_stores_the_seed_and_redirects_to_its_page(client, fake_builder):
    seed_id = generate_seed(client)
    with client.app.state.db.transaction() as conn:
        seed = conn.execute("SELECT * FROM seeds WHERE id = ?", (seed_id,)).fetchone()
        holes = conn.execute(
            "SELECT count(*) FROM seed_holes WHERE seed_id = ?", (seed_id,)
        ).fetchone()[0]
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


@pytest.mark.parametrize(
    "path", ["/h/0000000001", "/h/not-a-seed", "/h/0000000000", "/no-such-page"]
)
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
    assert re.search(r'name="par"\s+value="70"\s+checked', page)
    assert re.search(r'name="banned"\s+value="2W"\s+checked', page)
    assert seed_count(unwritten_client) == 0


def test_a_club_rule_refusal_names_its_values(unwritten_client):
    form = FormState.default()
    form.clubs_max = "2"
    form.required_bag = {"1W", "PW"}
    response = post_generate(unwritten_client, form)
    assert response.status_code == 400
    assert "generate.error.required_bag_over_max count=3 max=2" in response.text


def test_a_pool_that_cannot_fill_the_course_is_refused(catalog, curation, tmp_path):
    with app_client(
        strings=UNWRITTEN,
        builder=PoolTooSmall(catalog, curation, HoleStore(), tmp_path / "x.nes"),
    ) as test_client:
        response = post_generate(test_client)
        assert response.status_code == 400
        assert "generate.error.pool" in response.text
        assert seed_count(test_client) == 0


def test_generating_is_rate_limited_per_client(fake_builder):
    with app_client(
        strings=UNWRITTEN, builder=fake_builder, rate_limiter=RateLimiter(1, 3600)
    ) as test_client:
        assert (
            post_generate(test_client, **{"X-Forwarded-For": "192.0.2.1"}).status_code
            == 303
        )
        refused = post_generate(test_client, **{"X-Forwarded-For": "192.0.2.1"})
        assert refused.status_code == 429
        assert "generate.error.rate_limited" in refused.text
        assert (
            post_generate(test_client, **{"X-Forwarded-For": "192.0.2.2"}).status_code
            == 303
        )
        assert seed_count(test_client) == 2


def test_a_refused_form_spends_no_token(fake_builder):
    invalid = FormState.default()
    invalid.sources = set()
    with app_client(
        builder=fake_builder, rate_limiter=RateLimiter(1, 3600)
    ) as test_client:
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


def post_download(
    client: TestClient,
    seed_id: str,
    name: str = "luigi",
    clubs=("1W", "PW"),
    hashes=None,
):
    data = {
        "player_name": name,
        "clubs": list(clubs),
        **(ALL_HASHES if hashes is None else hashes),
    }
    return client.post(f"/h/{seed_id}/patch.ips", data=data)


def test_the_seed_page_offers_the_download_form(client):
    seed_id = generate_seed(client, seed_form(**US_ONLY, banned={"1W", "SW"}))
    page = client.get(f"/h/{seed_id}").text
    article = page[
        page.index('<article class="download"') : page.index(
            "</article>", page.index('<article class="download"')
        )
    ]
    assert 'data-state="checking"' in article
    assert f'data-required-roms="{US_ROM}"' in article
    assert f'data-filename="notgr_par72_{seed_id}.nes"' in article
    assert f'action="/h/{seed_id}/patch.ips"' in article
    assert re.search(r'name="player_name"\s+value="MARIO"\s+maxlength="10"', article)
    assert article.count('name="clubs"') == 15
    assert 'value="PT"' not in article
    assert re.search(r'name="clubs"\s+value="1W"\s+disabled', article)
    assert re.search(r'name="clubs"\s+value="SW"\s+disabled', article)
    assert re.search(r'name="clubs"\s+value="3W"\s+checked', article)
    assert not re.search(r'name="clubs"\s+value="4W"\s+checked', article)
    assert re.search(r'<button type="submit" disabled>', article)
    assert 'href="/rom"' in article
    assert 'id="download-strings"' in page
    assert (
        f'id="download-roms">{{"{US_ROM}": {{"sha1": "{vanilla_rom(US_ROM).sha1}"'
        in page
    )
    assert page.index('src="/static/romstore.js"') < page.index(
        'src="/static/download.js"'
    )


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
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="notgr_par{par}_{seed_id}.ips"'
    )
    manifest, unfinished_ips, options = fake_builder.finished
    assert manifest == fake_builder.built
    assert unfinished_ips == IPS
    assert options.player_name == "LUIGI"
    assert options.clubs == {Club.W1, Club.PW, Club.PT}
    assert fake_builder.credentials is None


def test_a_us_only_seed_needs_only_the_us_hash(client):
    seed_id = generate_seed(client, seed_form(**US_ONLY))
    assert post_download(client, seed_id, hashes=US_HASHES).status_code == 200


def test_a_seed_with_mario_open_content_is_refused_without_the_jp_hash(client):
    seed_id = generate_seed(client, seed_form(music="jp_france"))
    response = post_download(client, seed_id, hashes=US_HASHES)
    assert response.status_code == 403
    assert response.json() == {
        "error": "roms_missing",
        "values": {"roms": vanilla_rom(JP_ROM).title},
    }


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
        (
            {"banned": {"SW"}},
            "LUIGI",
            ("SW", "PW"),
            {"error": "clubs_banned", "values": {"clubs": "SW"}},
        ),
        (
            {"clubs_max": "2"},
            "LUIGI",
            ("1W", "PW"),
            {"error": "clubs_over_max", "values": {"count": 3, "max": 2}},
        ),
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


def test_downloading_without_the_servers_rom_is_unavailable(
    catalog, curation, tmp_path
):
    class NoRom(SeedBuilder):
        def build(self, manifest):
            return IPS

    with app_client(
        builder=NoRom(catalog, curation, HoleStore(), tmp_path / "missing.nes")
    ) as test_client:
        seed_id = generate_seed(test_client)
        response = post_download(test_client, seed_id)
        assert response.status_code == 503
        assert response.json() == {"error": "unavailable", "values": {}}


# -- Strings ----------------------------------------------------------------------------------


def test_written_strings_render_without_placeholders(fake_builder):
    written = _catalog_with_text(lambda key: f"TEXT:{key}")
    with app_client(strings=written, builder=fake_builder) as test_client:
        seed_id = generate_seed(test_client)
        scan = "/s/" + "A" * 48
        pages = {
            path: test_client.get(path).text
            for path in ("/", "/rom", "/generate", f"/h/{seed_id}", "/nope", scan)
        }
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
    assert "TEXT:scan_rejected.malformed" in pages[scan]


def test_unwritten_strings_render_as_placeholders_with_their_notes(fake_builder):
    unwritten = _catalog_with_text(lambda key: "")
    with app_client(strings=unwritten, builder=fake_builder) as test_client:
        rom = test_client.get("/rom").text
    assert "<title>⟦rom.page_title⟧</title>" in rom
    assert (
        '<span class="unwritten" title="ROM setup page h1">⟦rom.heading⟧</span>' in rom
    )
    assert f"⟦rom.expected_hash sha1={VANILLA_ROMS[0].sha1}⟧" in rom
    assert '"rom.status.stored": null' in rom


# -- Sign-in -----------------------------------------------------------------------------

DISCORD_CONFIG = Config(
    database=":memory:",
    discord_client_id="client-id",
    discord_client_secret="client-secret",
    session_secret="s",
)
NELLY = DiscordIdentity("80351110224678912", "nelly", "Nelly", "abc123")


class FakeDiscord(DiscordClient):
    """Answers every code with `identity`, or raises DiscordError when there is none."""

    def __init__(self, identity: DiscordIdentity | None = NELLY):
        super().__init__("client-id", "client-secret")
        self.identity = identity
        self.codes: list[tuple[str, str]] = []

    async def identify(self, code, redirect_uri):
        self.codes.append((code, redirect_uri))
        if self.identity is None:
            raise DiscordError("down")
        return self.identity


def users(client: TestClient) -> list[dict]:
    with client.app.state.db.transaction() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id")]


def dev_client(fake_builder, **kwargs) -> TestClient:
    return TestClient(
        create_app(
            Config(database=":memory:", dev_login=True), builder=fake_builder, **kwargs
        )
    )


def start_discord_sign_in(client: TestClient, next_path: str = "/generate") -> str:
    """Begin a Discord sign-in and return the state it sent Discord."""
    response = client.get(
        "/auth/login", params={"next": next_path}, follow_redirects=False
    )
    assert response.status_code == 303
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return query["state"][0]


def test_sign_in_is_hidden_and_missing_when_not_configured(unwritten_client):
    assert "nav.sign_in" not in unwritten_client.get("/").text
    assert unwritten_client.get("/auth/login").status_code == 404
    assert (
        unwritten_client.get(
            "/auth/callback", params={"state": "x", "code": "y"}
        ).status_code
        == 404
    )


def test_the_bypass_signs_in_as_the_named_user(fake_builder):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        assert "⟦nav.sign_in⟧" in test_client.get("/generate").text
        response = test_client.get(
            "/auth/login",
            params={"as": "alice", "next": "/generate"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/generate"
        page = test_client.get("/generate").text
        assert "⟦nav.signed_in_as name=alice⟧" in page
        assert "nav.sign_in⟧" not in page
        [alice] = users(test_client)
        assert (alice["discord_id"], alice["username"], alice["global_name"]) == (
            "dev:alice",
            "alice",
            None,
        )
        assert 1 <= alice["player_id"] <= 4294967295


def test_the_bypass_without_a_name_signs_in_as_dev(fake_builder):
    with dev_client(fake_builder) as test_client:
        assert (
            test_client.get("/auth/login", follow_redirects=False).headers["location"]
            == "/"
        )
        assert [user["discord_id"] for user in users(test_client)] == ["dev:dev"]


@pytest.mark.parametrize("name", ["", "a b", "x" * 33, "dev:alice"])
def test_the_bypass_refuses_odd_names(fake_builder, name):
    with dev_client(fake_builder) as test_client:
        assert test_client.get("/auth/login", params={"as": name}).status_code == 400
        assert users(test_client) == []


def test_the_bypass_is_refused_off_localhost(fake_builder):
    with pytest.raises(ConfigError):
        create_app(
            Config(
                database=":memory:", dev_login=True, base_url="https://golf.example"
            ),
            builder=fake_builder,
        )


def test_signing_out_clears_the_session_and_returns(fake_builder):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        test_client.get("/auth/login", params={"as": "alice"})
        page = test_client.get("/rom").text
        assert '<input type="hidden" name="next" value="/rom">' in page
        response = test_client.post(
            "/auth/logout", data={"next": "/rom"}, follow_redirects=False
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/rom"
        assert "⟦nav.sign_in⟧" in test_client.get("/rom").text


def test_the_sign_in_link_returns_to_the_current_page(fake_builder):
    with dev_client(fake_builder) as test_client:
        assert (
            'href="/auth/login?next=/generate%3Fpar%3D71"'
            in test_client.get("/generate?par=71").text
        )


@pytest.mark.parametrize("next_path", ["https://evil.example/", "//evil.example/"])
def test_sign_in_never_returns_off_site(fake_builder, next_path):
    with dev_client(fake_builder) as test_client:
        response = test_client.get(
            "/auth/login",
            params={"as": "alice", "next": next_path},
            follow_redirects=False,
        )
        assert response.headers["location"] == "/"
        response = test_client.post(
            "/auth/logout", data={"next": next_path}, follow_redirects=False
        )
        assert response.headers["location"] == "/"


def test_a_session_for_a_missing_user_is_signed_out(fake_builder):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        test_client.get("/auth/login", params={"as": "alice"})
        with test_client.app.state.db.transaction() as conn:
            conn.execute("DELETE FROM users")
        assert "⟦nav.sign_in⟧" in test_client.get("/").text


def test_the_session_cookie_is_lax_and_secure_only_on_https(fake_builder):
    with dev_client(fake_builder) as test_client:
        cookie = test_client.get(
            "/auth/login", params={"as": "alice"}, follow_redirects=False
        ).headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "samesite=lax" in cookie.lower()
    assert "secure" not in cookie.lower()
    https = replace(DISCORD_CONFIG, base_url="https://golf.example")
    with TestClient(
        create_app(https, builder=fake_builder, discord=FakeDiscord()),
        base_url="https://golf.example",
    ) as test_client:
        cookie = test_client.get("/auth/login", follow_redirects=False).headers[
            "set-cookie"
        ]
    assert "secure" in cookie.lower()


def test_discord_sign_in_redirects_to_discord_with_a_state(fake_builder):
    with TestClient(create_app(DISCORD_CONFIG, builder=fake_builder)) as test_client:
        response = test_client.get("/auth/login", follow_redirects=False)
    location = urlsplit(response.headers["location"])
    assert (
        f"{location.scheme}://{location.netloc}{location.path}"
        == "https://discord.com/oauth2/authorize"
    )
    query = parse_qs(location.query)
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8000/auth/callback"]
    assert len(query["state"][0]) >= 32


def test_discord_sign_in_records_the_user_and_returns(fake_builder):
    discord = FakeDiscord()
    with TestClient(
        create_app(
            DISCORD_CONFIG, strings=UNWRITTEN, builder=fake_builder, discord=discord
        )
    ) as test_client:
        state = start_discord_sign_in(test_client)
        response = test_client.get(
            "/auth/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/generate"
        assert discord.codes == [("abc", "http://127.0.0.1:8000/auth/callback")]
        assert "⟦nav.signed_in_as name=Nelly⟧" in test_client.get("/").text
        [nelly] = users(test_client)
        assert (
            nelly["discord_id"],
            nelly["username"],
            nelly["global_name"],
            nelly["avatar"],
        ) == (
            "80351110224678912",
            "nelly",
            "Nelly",
            "abc123",
        )
        # The state is spent: replaying the callback does not sign in again.
        replay = test_client.get(
            "/auth/callback", params={"code": "abc", "state": state}
        )
        assert replay.status_code == 400
        assert "⟦sign_in_failed.expired⟧" in replay.text


@pytest.mark.parametrize("params", [{"code": "abc", "state": "wrong"}, {"code": "abc"}])
def test_a_callback_whose_state_does_not_match_is_refused(fake_builder, params):
    discord = FakeDiscord()
    with TestClient(
        create_app(
            DISCORD_CONFIG, strings=UNWRITTEN, builder=fake_builder, discord=discord
        )
    ) as test_client:
        start_discord_sign_in(test_client)
        response = test_client.get("/auth/callback", params=params)
        assert response.status_code == 400
        assert "⟦sign_in_failed.expired⟧" in response.text
        assert "sign_in_failed.unavailable" not in response.text
        assert discord.codes == []
        assert users(test_client) == []


def test_turning_discord_down_returns_signed_out(fake_builder):
    discord = FakeDiscord()
    with TestClient(
        create_app(
            DISCORD_CONFIG, strings=UNWRITTEN, builder=fake_builder, discord=discord
        )
    ) as test_client:
        state = start_discord_sign_in(test_client, "/rom")
        response = test_client.get(
            "/auth/callback",
            params={"error": "access_denied", "state": state},
            follow_redirects=False,
        )
        assert response.headers["location"] == "/rom"
        assert discord.codes == []
        assert "⟦nav.sign_in⟧" in test_client.get("/rom").text


def test_discord_failing_shows_unavailable(fake_builder):
    with TestClient(
        create_app(
            DISCORD_CONFIG,
            strings=UNWRITTEN,
            builder=fake_builder,
            discord=FakeDiscord(None),
        )
    ) as test_client:
        state = start_discord_sign_in(test_client)
        response = test_client.get(
            "/auth/callback", params={"code": "abc", "state": state}
        )
        assert response.status_code == 502
        assert "⟦sign_in_failed.unavailable⟧" in response.text
        assert 'href="/auth/login?next=/"' in response.text
        assert users(test_client) == []


def test_a_seed_records_the_player_who_generated_it(fake_builder):
    with dev_client(fake_builder) as test_client:
        guest_seed = generate_seed(test_client)
        test_client.get("/auth/login", params={"as": "alice"})
        signed_in_seed = generate_seed(test_client)
        [alice] = users(test_client)
        with test_client.app.state.db.transaction() as conn:
            creators = dict(conn.execute("SELECT id, creator_id FROM seeds").fetchall())
    assert creators == {guest_seed: None, signed_in_seed: alice["id"]}


def test_signed_in_players_are_rate_limited_per_user(fake_builder):
    with dev_client(fake_builder, rate_limiter=RateLimiter(1, 3600)) as test_client:
        same_address = {"X-Forwarded-For": "192.0.2.1"}
        test_client.get("/auth/login", params={"as": "alice"})
        assert post_generate(test_client, **same_address).status_code == 303
        assert post_generate(test_client, **same_address).status_code == 429
        test_client.get("/auth/login", params={"as": "bob"})
        assert post_generate(test_client, **same_address).status_code == 303
        test_client.post("/auth/logout")
        assert post_generate(test_client, **same_address).status_code == 303
        assert seed_count(test_client) == 3


# -- Entries -----------------------------------------------------------------------------


def entries(client: TestClient) -> list[dict]:
    with client.app.state.db.transaction() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM entries ORDER BY id")]


def qr_seed_id(client: TestClient, seed_id: str) -> int:
    with client.app.state.db.transaction() as conn:
        return conn.execute(
            "SELECT qr_seed_id FROM seeds WHERE id = ?", (seed_id,)
        ).fetchone()[0]


def test_a_signed_out_download_records_no_entry(fake_builder):
    with dev_client(fake_builder) as test_client:
        seed_id = generate_seed(test_client)
        assert post_download(test_client, seed_id).status_code == 200
        assert fake_builder.credentials is None
        assert entries(test_client) == []


def test_a_signed_in_download_enters_the_seed_and_finishes_with_credentials(
    fake_builder,
):
    with dev_client(fake_builder) as test_client:
        seed_id = generate_seed(test_client)
        test_client.get("/auth/login", params={"as": "alice"})
        response = post_download(test_client, seed_id, name="luigi", clubs=("1W", "PW"))
        assert response.status_code == 200
        assert response.content == FINISHED
        [alice] = users(test_client)
        [entry] = entries(test_client)
        expected_seed_id = qr_seed_id(test_client, seed_id)
    assert entry["seed_id"] == seed_id
    assert entry["user_id"] == alice["id"]
    assert entry["player_name"] == "LUIGI"
    assert entry["clubs"] == "1W PW PT"
    credentials = fake_builder.credentials
    assert credentials.seed_id == expected_seed_id.to_bytes(8, "big")
    assert credentials.player_ids == (alice["player_id"].to_bytes(4, "big"),) * 2
    assert credentials.keys == (entry["key_slot0"], entry["key_slot1"])
    assert entry["key_slot0"] != entry["key_slot1"]


def test_downloading_again_updates_the_entry_and_keeps_its_keys(fake_builder):
    with dev_client(fake_builder) as test_client:
        seed_id = generate_seed(test_client)
        test_client.get("/auth/login", params={"as": "alice"})
        post_download(test_client, seed_id, name="luigi", clubs=("1W", "PW"))
        first_keys = fake_builder.credentials.keys
        post_download(test_client, seed_id, name="toad", clubs=("3W", "SW"))
        [entry] = entries(test_client)
    assert fake_builder.credentials.keys == first_keys
    assert (entry["player_name"], entry["clubs"]) == ("TOAD", "3W SW PT")


def test_players_entering_the_same_seed_get_their_own_entries_and_keys(fake_builder):
    with dev_client(fake_builder) as test_client:
        seed_id = generate_seed(test_client)
        test_client.get("/auth/login", params={"as": "alice"})
        post_download(test_client, seed_id)
        alice_credentials = fake_builder.credentials
        test_client.get("/auth/login", params={"as": "bob"})
        post_download(test_client, seed_id)
        bob_credentials = fake_builder.credentials
        assert len(entries(test_client)) == 2
    assert alice_credentials.seed_id == bob_credentials.seed_id
    assert alice_credentials.player_ids != bob_credentials.player_ids
    assert set(alice_credentials.keys).isdisjoint(bob_credentials.keys)


@pytest.mark.parametrize("change", [{"name": "LU1GI"}, {"hashes": {}}])
def test_a_refused_download_records_no_entry(fake_builder, change):
    with dev_client(fake_builder) as test_client:
        seed_id = generate_seed(test_client)
        test_client.get("/auth/login", params={"as": "alice"})
        assert post_download(test_client, seed_id, **change).status_code in (400, 403)
        assert entries(test_client) == []


def test_the_seed_page_tells_only_signed_out_players_the_rom_is_a_guest_rom(
    fake_builder,
):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        seed_id = generate_seed(test_client)
        signed_out = test_client.get(f"/h/{seed_id}").text
        test_client.get("/auth/login", params={"as": "alice"})
        signed_in = test_client.get(f"/h/{seed_id}").text
    assert "seed.download.guest_notice" in signed_out
    assert f'href="/auth/login?next=/h/{seed_id}"' in signed_out
    assert "seed.download.guest_notice" not in signed_in


def test_the_seed_page_has_no_guest_notice_without_sign_in(unwritten_client):
    seed_id = generate_seed(unwritten_client)
    assert (
        "seed.download.guest_notice" not in unwritten_client.get(f"/h/{seed_id}").text
    )


def test_my_page_needs_sign_in(fake_builder, client):
    with dev_client(fake_builder) as test_client:
        response = test_client.get("/me", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login?next=/me"
    assert client.get("/me").status_code == 404


def test_my_page_lists_only_my_entries_newest_first(fake_builder):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        test_client.get("/auth/login", params={"as": "alice"})
        assert "me.entries.none" in test_client.get("/me").text
        first = generate_seed(test_client)
        second = generate_seed(test_client)
        post_download(test_client, first, name="luigi", clubs=("1W", "PW"))
        test_client.get("/auth/login", params={"as": "bob"})
        post_download(test_client, second, name="toad")
        bob_page = test_client.get("/me").text
        test_client.get("/auth/login", params={"as": "alice"})
        post_download(test_client, second, name="peach")
        with test_client.app.state.db.transaction() as conn:
            conn.execute(
                "UPDATE entries SET created_at = '2026-01-01T00:00:00Z' WHERE seed_id = ?",
                (first,),
            )
        alice_page = test_client.get("/me").text
    assert 'aria-current="page"' in alice_page[: alice_page.index("</nav>")]
    assert "me.entries.none" not in alice_page
    assert alice_page.index(f'href="/h/{second}"') < alice_page.index(
        f'href="/h/{first}"'
    )
    assert "<td>LUIGI</td>" in alice_page
    assert "<td>1W PW PT</td>" in alice_page
    assert "<td>PEACH</td>" in alice_page
    assert "<td>TOAD</td>" not in alice_page
    assert f'href="/h/{first}"' not in bob_page


# -- Submissions -------------------------------------------------------------------------


def scan_path(
    client: TestClient,
    seed_id: str,
    username: str,
    slot: int = 0,
    strokes: int = 4,
    key=None,
) -> str:
    """The path a ROM's QR code opens: username's entry in the seed, every hole `strokes` with 2 putts."""
    with client.app.state.db.transaction() as conn:
        row = conn.execute(
            """
            SELECT seeds.qr_seed_id, users.player_id, entries.key_slot0, entries.key_slot1
            FROM entries JOIN seeds ON seeds.id = entries.seed_id JOIN users ON users.id = entries.user_id
            WHERE entries.seed_id = ? AND users.username = ?
            """,
            (seed_id, username),
        ).fetchone()
    round_payload = RoundPayload(
        seed_id=row["qr_seed_id"].to_bytes(8, "big"),
        player_id=row["player_id"].to_bytes(4, "big"),
        holes=(HoleRecord(strokes, 2),) * 18,
        player_slot=slot,
    )
    signing_key = (
        key
        if key is not None
        else bytes(row["key_slot1"] if slot else row["key_slot0"])
    )
    return "/s/" + round_payload.to_url(signing_key).removeprefix(URL_PREFIX)


def entered_seed(test_client: TestClient, *names: str) -> str:
    """A seed each named dev user has downloaded signed in; signed in as the last of them."""
    seed_id = generate_seed(test_client)
    for name in names:
        test_client.get("/auth/login", params={"as": name})
        assert post_download(test_client, seed_id).status_code == 200
    return seed_id


def recorded_rounds(client: TestClient) -> list[dict]:
    with client.app.state.db.transaction() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM rounds ORDER BY id")]


def test_scanning_records_the_round_and_redirects_to_its_permalink(fake_builder):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        seed_id = entered_seed(test_client, "alice")
        test_client.post("/auth/logout", data={"next": "/"})
        response = test_client.get(
            scan_path(test_client, seed_id, "alice", strokes=5), follow_redirects=False
        )
        recorded = recorded_rounds(test_client)
        page = test_client.get(response.headers["location"])
    assert response.status_code == 303
    assert response.headers["cache-control"] == "no-store"
    assert [
        (row["slot"], row["total_strokes"], row["total_putts"]) for row in recorded
    ] == [(0, 90, 36)]
    assert response.headers["location"] == f"/r/{recorded[0]['public_id']}?recorded"
    assert page.status_code == 200
    assert "round.heading_recorded" in page.text
    assert "round.player_one name=alice" in page.text
    assert f'href="/h/{seed_id}"' in page.text
    assert '<td class="num over-par">5</td>' in page.text
    assert '<td class="num over-par">90</td>' in page.text


def test_the_permalink_confirms_the_round_only_for_the_scan_that_recorded_it(
    fake_builder,
):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        seed_id = entered_seed(test_client, "alice")
        test_client.get(scan_path(test_client, seed_id, "alice", strokes=5))
        [row] = recorded_rounds(test_client)
        confirmed = test_client.get(f"/r/{row['public_id']}?recorded")
        plain = test_client.get(f"/r/{row['public_id']}")
    for page in (confirmed, plain):
        assert page.status_code == 200
        # a permalink is an ordinary page: unlike /s/, it may be cached
        assert "cache-control" not in page.headers
        assert '<td class="num over-par">90</td>' in page.text
    assert "round.heading_recorded" in confirmed.text
    assert "history.replaceState" in confirmed.text
    assert "round.heading" in plain.text
    assert "round.heading_recorded" not in plain.text
    assert "history.replaceState" not in plain.text


@pytest.mark.parametrize("round_id", ["0123456789", "not-an-id", "", "short"])
def test_a_permalink_naming_no_round_is_not_found(fake_builder, round_id):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        assert test_client.get(f"/r/{round_id}").status_code == 404


def test_scanning_again_reaches_the_first_round_and_records_nothing(fake_builder):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        seed_id = entered_seed(test_client, "alice")
        path = scan_path(test_client, seed_id, "alice", strokes=5)
        first = test_client.get(path, follow_redirects=False)
        again = test_client.get(path, follow_redirects=False)
        different = test_client.get(
            scan_path(test_client, seed_id, "alice", strokes=3), follow_redirects=False
        )
        recorded = recorded_rounds(test_client)
        pages = [
            test_client.get(response.headers["location"])
            for response in (again, different)
        ]
    permalink = f"/r/{recorded[0]['public_id']}"
    assert first.headers["location"] == f"{permalink}?recorded"
    # a rescan lands on the same round, without the confirmation the first scan earned
    for response in (again, different):
        assert response.status_code == 303
        assert response.headers["location"] == permalink
    for page in pages:
        assert "round.heading_recorded" not in page.text
        assert '<td class="num over-par">90</td>' in page.text
    assert len(recorded) == 1


def test_strokes_are_marked_against_par(fake_builder):
    with dev_client(fake_builder) as test_client:
        seed_id = entered_seed(test_client, "alice")
        course = fake_builder.built.course
        page = test_client.get(scan_path(test_client, seed_id, "alice", strokes=4)).text
    pars = [hole.par for hole in course.holes]
    assert course.par == 72
    # a 4 on every hole: over a par 3, under a par 5, and level par over the round
    assert page.count('<td class="num over-par">4</td>') == pars.count(3)
    assert page.count('<td class="num under-par">4</td>') == pars.count(5)
    assert page.count('<td class="num">72</td>') == 2


def test_a_player_two_scan_is_marked_on_the_page(fake_builder):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        seed_id = entered_seed(test_client, "alice")
        response = test_client.get(scan_path(test_client, seed_id, "alice", slot=1))
    assert response.status_code == 200
    assert "round.player_two name=alice" in response.text


@pytest.mark.parametrize(
    "path, status, notice",
    [
        ("/s/" + "A" * 48, 400, "malformed"),
        ("/s/" + "A" * 20, 400, "malformed"),
        ("/s/" + "AQ" + "A" * 46, 400, "unfinished"),
    ],
)
def test_scans_that_are_not_rounds_are_refused(fake_builder, path, status, notice):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        response = test_client.get(path)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "scan_rejected.heading" in response.text
    assert f"scan_rejected.{notice}" in response.text


def test_a_scan_signed_with_the_wrong_key_is_not_recognized(fake_builder):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        seed_id = entered_seed(test_client, "alice")
        response = test_client.get(
            scan_path(test_client, seed_id, "alice", key=bytes(8))
        )
        assert recorded_rounds(test_client) == []
    assert response.status_code == 404
    assert "scan_rejected.unrecognized" in response.text


def test_the_seed_page_lists_recorded_rounds(fake_builder):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        seed_id = entered_seed(test_client, "alice", "bob")
        assert "seed.rounds.none" in test_client.get(f"/h/{seed_id}").text
        test_client.get(scan_path(test_client, seed_id, "alice", strokes=5))
        test_client.get(scan_path(test_client, seed_id, "alice", slot=1, strokes=6))
        test_client.get(scan_path(test_client, seed_id, "bob", strokes=4))
        page = test_client.get(f"/h/{seed_id}").text
    assert "seed.rounds.none" not in page
    rounds = page[page.index('class="rounds') :]
    assert (
        rounds.index(">bob</a>")
        < rounds.index(">alice</a>")
        < rounds.index("seed.rounds.player_two name=alice")
    )
    # every listed round links to its own permalink
    assert len(set(re.findall(r'href="(/r/\w{10})"', rounds))) == 3


def test_my_page_lists_my_rounds(fake_builder):
    with dev_client(fake_builder, strings=UNWRITTEN) as test_client:
        seed_id = entered_seed(test_client, "bob", "alice")
        assert "me.rounds.none" in test_client.get("/me").text
        test_client.get(scan_path(test_client, seed_id, "alice", slot=1, strokes=5))
        test_client.get(scan_path(test_client, seed_id, "bob", strokes=3))
        player_two_only = test_client.get("/me").text
        test_client.get(scan_path(test_client, seed_id, "alice", slot=0, strokes=4))
        page = test_client.get("/me").text
    assert "me.rounds.none" not in page
    rounds = page[page.index('class="rounds') :]
    # only the player 2 round's magic words carry the asterisk
    assert rounds.count("</a>*</td>") == 1
    assert rounds.count('class="magic-words"') == 3
    assert len(set(re.findall(r'href="(/r/\w{10})"', rounds))) == 2
    assert "</a>*</td>" in player_two_only[player_two_only.index('class="rounds') :]
    assert ">90</a>" in rounds
    assert ">54</a>" not in rounds


def test_downloading_after_a_round_finishes_with_the_new_choices_and_leaves_the_entry(
    fake_builder,
):
    with dev_client(fake_builder) as test_client:
        seed_id = entered_seed(test_client, "alice")
        first_keys = fake_builder.credentials.keys
        test_client.get(scan_path(test_client, seed_id, "alice"))
        before = entries(test_client)
        response = post_download(test_client, seed_id, name="toad", clubs=("3W", "SW"))
        after = entries(test_client)
    assert response.status_code == 200
    _, _, options = fake_builder.finished
    assert options.player_name == "TOAD"
    assert options.clubs == frozenset({Club.W3, Club.SW, Club.PT})
    assert fake_builder.credentials.keys == first_keys
    assert after == before
