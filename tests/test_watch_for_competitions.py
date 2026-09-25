"""
Tests against real captured homepage HTML for the 4 South-East London
stations (tests/fixtures/southeast_london_*_homepage.html, captured live
2026-09-09) — same "test against something real" convention as every
other adapter here, applied to the watcher's detection step rather than a
classifier. All 4 correctly find nothing at capture time, matching the
real investigation (no live competition existed on any of them then) —
the positive-detection path is tested against a synthetic fixture with an
injected "Win" link, since none of the 4 real ones currently has one.
"""

from __future__ import annotations

from pathlib import Path

from radiocomp.models import Station
from radiocomp.stations.watch_for_competitions import check_for_competition_link, watch_for_new_competitions

FIXTURES = Path(__file__).parent / "fixtures"

_REAL_HOMEPAGES = {
    "select_radio": ("https://selectradioapp.com/", FIXTURES / "southeast_london_select_radio_homepage.html"),
    "rainbow_radio": ("https://www.rainbowradio.co.uk/", FIXTURES / "southeast_london_rainbow_radio_homepage.html"),
    "mi_soul": ("https://mi-soul.com/", FIXTURES / "southeast_london_mi_soul_homepage.html"),
    "resonance_fm": ("https://www.resonancefm.com/", FIXTURES / "southeast_london_resonance_fm_homepage.html"),
}


def _serve_fixture(monkeypatch, html: str, status_code: int = 200):
    """Monkeypatch httpx.get to return this fixture's content instead of
    hitting the real network — same fixture-derived-data convention as
    every other adapter, just via monkeypatch since this module calls
    httpx.get directly rather than exposing a separate fetch() to import."""
    import httpx

    class _FakeResponse:
        def __init__(self, text, status_code):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("error", request=None, response=self)

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(html, status_code))


def test_all_four_real_homepages_currently_find_nothing(monkeypatch):
    # Documents the real state at fixture-capture time (2026-09-09) — no
    # live competition existed on any of these 4 stations then. Not a
    # design assumption; if this starts failing because a real
    # competition now exists, that's the watcher doing its job — update
    # the fixture, not this assertion, when that happens for real.
    for name, (url, path) in _REAL_HOMEPAGES.items():
        import httpx as httpx_module

        html = path.read_text()

        class _FakeResponse:
            def raise_for_status(self):
                pass

        resp = _FakeResponse()
        resp.text = html
        monkeypatch.setattr(httpx_module, "get", lambda *a, **k: resp)

        assert check_for_competition_link(url) is None, f"{name} unexpectedly matched"


def test_synthetic_win_link_is_detected(monkeypatch):
    # Synthetic — none of the 4 real fixtures currently has a competition
    # link to test the positive path against.
    html = """
    <html><body>
      <nav>
        <a href="/about">About</a>
        <a href="/win/summer-giveaway">Win our Summer Giveaway!</a>
        <a href="/contact">Contact</a>
      </nav>
    </body></html>
    """
    _serve_fixture(monkeypatch, html)

    result = check_for_competition_link("https://example.com/")

    assert result == "https://example.com/win/summer-giveaway"


def test_link_text_matching_is_case_insensitive_and_matches_prize_too():
    from bs4 import BeautifulSoup

    from radiocomp.stations.watch_for_competitions import _LINK_TEXT_RE

    assert _LINK_TEXT_RE.search("WIN A HOLIDAY")
    assert _LINK_TEXT_RE.search("Competitions")
    assert _LINK_TEXT_RE.search("Latest Prizes")
    assert not _LINK_TEXT_RE.search("About Us")


def test_fetch_failure_returns_none_not_an_exception(monkeypatch):
    import httpx

    def _boom(*a, **k):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(httpx, "get", _boom)

    assert check_for_competition_link("https://example.com/") is None


def test_watch_for_new_competitions_only_fires_once_per_link(monkeypatch, tmp_path):
    from radiocomp import config

    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)

    html = '<html><body><a href="/win/big-prize">Win a Big Prize</a></body></html>'
    _serve_fixture(monkeypatch, html)

    station = Station(name="Test Station", base_urls=["https://example.com/"], is_local_independent=True)

    first_run = watch_for_new_competitions([station])
    assert len(first_run) == 1
    assert first_run[0][0].name == "Test Station"
    assert first_run[0][1] == "https://example.com/win/big-prize"

    # Same link, second run — must not fire again.
    second_run = watch_for_new_competitions([station])
    assert second_run == []


def test_watch_for_new_competitions_fires_again_if_the_link_actually_changes(monkeypatch, tmp_path):
    from radiocomp import config

    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)

    station = Station(name="Test Station", base_urls=["https://example.com/"], is_local_independent=True)

    _serve_fixture(monkeypatch, '<html><body><a href="/win/first">Win First Prize</a></body></html>')
    first_run = watch_for_new_competitions([station])
    assert len(first_run) == 1

    _serve_fixture(monkeypatch, '<html><body><a href="/win/second">Win Second Prize</a></body></html>')
    second_run = watch_for_new_competitions([station])
    assert len(second_run) == 1
    assert second_run[0][1] == "https://example.com/win/second"
