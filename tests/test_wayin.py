"""
Tests against real captured HTML (tests/fixtures/wayin_*.html, captured
live 2026-09-11) — same "test against something real, not mocked-up
sample data" convention as every other adapter here.

Fixtures:
- wayin_kmfm_linking_page.html — KMFM's own /win/ page, a plain
  server-rendered page with a real <a href> to its wayin.com campaign.
- wayin_bauer_linking_page.html — Hits Radio's (Bauer/Rayo's) own
  competitions/win article page for a Tesco Clubcard competition — a
  client-rendered Next.js app whose wayin.com URL lives only inside its
  embedded __NEXT_DATA__ JSON, not a real <a href> (see wayin.py's module
  docstring for why find_wayin_links() has to look two ways).
- wayin_kmfm_gousto_campaign_page.html — the real wayin.com campaign
  page KMFM's link points to (a Gousto-sponsored "Ultimate Kitchen
  Upgrade"), whose own T&Cs state "Online entry is free of charge."
  verbatim — the one real confident free signal found so far.
- wayin_bauer_tesco_campaign_page.html — the real wayin.com campaign page
  the Bauer/Rayo fixture points to. Its static HTML has no T&Cs/cost
  language at all, so it's the real example of the conservative
  "couldn't classify, review_recommended=True" path.

No live network call is ever made in these tests — find_wayin_links()
calls httpx.get() directly (matching watch_for_competitions.py's own
convention), so it's exercised here via monkeypatching httpx.get to serve
the saved fixture text, same technique as
tests/test_watch_for_competitions.py.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from radiocomp.models import EntryChannelType
from radiocomp.stations.wayin import (
    _SEED_LINK_SOURCES,
    fetch_campaign,
    find_wayin_links,
    parse_detail,
)

FIXTURES = Path(__file__).parent / "fixtures"

KMFM_LINKING_PAGE = (FIXTURES / "wayin_kmfm_linking_page.html").read_text()
BAUER_LINKING_PAGE = (FIXTURES / "wayin_bauer_linking_page.html").read_text()
KMFM_CAMPAIGN_PAGE = (FIXTURES / "wayin_kmfm_gousto_campaign_page.html").read_text()
BAUER_CAMPAIGN_PAGE = (FIXTURES / "wayin_bauer_tesco_campaign_page.html").read_text()

_REAL_KMFM_CAMPAIGN_URL = "https://xd.wayin.com/display/container/dc/07806756-2ab1-4ac3-a752-462142a2c175/details"
_REAL_BAUER_CAMPAIGN_URL = "https://x.wayin.com/display/container/dc/49fbb4f2-06d4-4c76-bdd0-9b16a79205de/details"


def _serve(monkeypatch, text: str, status_code: int = 200):
    class _FakeResponse:
        def __init__(self):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("error", request=None, response=self)

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse())


def test_seed_link_sources_shape():
    # Both real seed entries must be present with the fields ingest()
    # actually relies on — a config typo here would silently mean this
    # adapter scans nothing.
    assert len(_SEED_LINK_SOURCES) == 2
    for source in _SEED_LINK_SOURCES:
        assert source["page_url"].startswith("https://")
        assert source["station_name_raw"]
        assert source["network"]


def test_find_wayin_links_on_real_kmfm_linking_page(monkeypatch):
    # KMFM's real page has a literal <a href="https://xd.wayin.com/...">
    # link — the simple case the plan originally assumed would be enough.
    _serve(monkeypatch, KMFM_LINKING_PAGE)

    links = find_wayin_links("https://www.kmfm.co.uk/win/")

    assert links == [_REAL_KMFM_CAMPAIGN_URL]


def test_find_wayin_links_on_real_bauer_linking_page_needs_the_raw_scan(monkeypatch):
    # Rayo's real page has NO <a href> to wayin.com at all — the URL only
    # exists as a string inside the page's embedded __NEXT_DATA__ JSON.
    # This is the real case that proved a bare BeautifulSoup <a> scan
    # (the plan's original assumption) finds nothing here.
    _serve(monkeypatch, BAUER_LINKING_PAGE)

    links = find_wayin_links(
        "https://www.hellorayo.co.uk/hits-radio/competitions/win/tesco-clubcard-september-26-sponsored"
    )

    assert _REAL_BAUER_CAMPAIGN_URL in links


def test_find_wayin_links_returns_empty_list_not_exception_on_fetch_failure(monkeypatch):
    def _boom(*a, **k):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(httpx, "get", _boom)

    assert find_wayin_links("https://example.com/win/") == []


def test_find_wayin_links_returns_empty_list_when_no_wayin_link_present(monkeypatch):
    _serve(monkeypatch, "<html><body><a href='/about'>About</a></body></html>")

    assert find_wayin_links("https://example.com/") == []


def test_fetch_campaign_returns_real_html(monkeypatch):
    _serve(monkeypatch, KMFM_CAMPAIGN_PAGE)

    html = fetch_campaign(_REAL_KMFM_CAMPAIGN_URL)

    assert html == KMFM_CAMPAIGN_PAGE


def test_fetch_campaign_raises_on_http_error(monkeypatch):
    _serve(monkeypatch, "not found", status_code=404)

    import pytest

    with pytest.raises(httpx.HTTPError):
        fetch_campaign(_REAL_KMFM_CAMPAIGN_URL)


def test_parse_detail_real_kmfm_campaign_extracts_title_deadline_and_confident_free_signal():
    promo, channels = parse_detail(KMFM_CAMPAIGN_PAGE, _REAL_KMFM_CAMPAIGN_URL, "KMFM", "Bauer")

    assert promo is not None
    assert promo.title == "Gousto - Online Competition"
    assert promo.station_name_raw == "KMFM"
    assert promo.network == "Bauer"
    assert promo.source_url == _REAL_KMFM_CAMPAIGN_URL
    assert promo.discovered_via.value == "direct"
    # Real closing date confirmed from the page's own T&Cs: "to Friday
    # 11th September 2026 at 23:59 ("End Time")".
    assert promo.entry_deadline is not None
    assert promo.entry_deadline.isoformat() == "2026-09-11"
    # Neither real campaign states a single cash prize figure.
    assert promo.prize_value_gbp is None

    assert len(channels) == 1
    channel = channels[0]
    assert channel.channel_type == EntryChannelType.WEB_FORM
    # The one real confident signal found so far: "Online entry is free
    # of charge." verbatim in the page's own T&Cs.
    assert channel.is_free_route is True
    assert channel.cost_to_entrant_gbp == 0.0
    assert channel.review_recommended is False
    assert "free of charge" in channel.raw_excerpt.lower()


def test_parse_detail_real_bauer_campaign_has_no_free_paid_signal_so_stays_ambiguous():
    promo, channels = parse_detail(BAUER_CAMPAIGN_PAGE, _REAL_BAUER_CAMPAIGN_URL, "Bauer", "Bauer")

    assert promo is not None
    assert promo.title == "Tesco Clubcard - HITS - Online Competition [April 2026]"
    # Real closing date confirmed from the page's own copy: "closes on
    # Wednesday 30th September 2026 at 23:59."
    assert promo.entry_deadline is not None
    assert promo.entry_deadline.isoformat() == "2026-09-30"
    assert promo.prize_value_gbp is None

    assert len(channels) == 1
    channel = channels[0]
    assert channel.channel_type == EntryChannelType.WEB_FORM
    # No cost/charge language exists anywhere in this real page's static
    # HTML — never guessed "free" just because there's no payment field.
    assert channel.is_free_route is None
    assert channel.cost_to_entrant_gbp is None
    assert channel.review_recommended is True


def test_parse_detail_missing_title_returns_none_promotion_not_an_exception():
    html = "<html><body><p>This page has no title tag at all.</p></body></html>"

    promo, channels = parse_detail(html, "https://xd.wayin.com/display/container/dc/deadbeef/details", "KMFM", "Bauer")

    assert promo is None
    assert channels == []


def test_parse_detail_empty_html_degrades_safely():
    promo, channels = parse_detail("", "https://xd.wayin.com/display/container/dc/deadbeef/details", "KMFM", "Bauer")

    assert promo is None
    assert channels == []


def test_parse_detail_title_present_but_no_entry_period_text_leaves_deadline_none():
    html = "<html><head><title>Some Competition</title></head><body><p>No dates mentioned here.</p></body></html>"

    promo, channels = parse_detail(
        html, "https://xd.wayin.com/display/container/dc/deadbeef/details", "KMFM", "Bauer"
    )

    assert promo is not None
    assert promo.entry_deadline is None
    assert channels[0].is_free_route is None
    assert channels[0].review_recommended is True
