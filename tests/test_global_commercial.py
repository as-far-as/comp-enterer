"""
Tests against real captured HTML (tests/fixtures/global_commercial_nescafe_2026_*.html,
fetched live from comp.smoothradio.com/campaign.smoothradio.com on 2026-10-05/06) —
same "test against something real, not mocked-up sample data" convention as every
other adapter here.

Fixtures:
- global_commercial_nescafe_2026_page.html — the real, full server-rendered
  competition page (https://comp.smoothradio.com/nescafe-2026/8), including its
  Next.js flight-data script blobs.
- global_commercial_nescafe_2026_terms.html — the real T&Cs page linked from that
  competition's own campaign.terms_url. Confirmed live to contain neither an
  explicit free- nor paid-entry phrase anywhere in its body — see
  stations/global_commercial.py's own docstring for why this means the one real
  example built against this adapter still comes back
  is_free_route=None/review_recommended=True, not assumed free.

No live network call is ever made in these tests.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx

from radiocomp import config
from radiocomp.models import DiscoveredVia, EntryChannelType
from radiocomp.stations.global_commercial import (
    STATION_NAME,
    STATION_NETWORK,
    _classify_free_paid,
    _tandc_text,
    extract_competition_json,
    parse_detail,
)

FIXTURES = Path(__file__).parent / "fixtures"
PAGE_HTML = (FIXTURES / "global_commercial_nescafe_2026_page.html").read_text(encoding="utf-8")
TERMS_HTML = (FIXTURES / "global_commercial_nescafe_2026_terms.html").read_text(encoding="utf-8")
SOURCE_URL = "https://comp.smoothradio.com/nescafe-2026/8"


# --- extract_competition_json() — against the real fixture ----------------


def test_extract_competition_json_finds_the_real_embedded_document():
    doc = extract_competition_json(PAGE_HTML)

    assert doc is not None
    assert doc["slug"] == "nescafe-2026"
    # The Sanity doc's own internal "title" field vs. the real human-facing
    # metaTitle — see parse_detail()'s own preference for metaTitle.
    assert doc["title"] == "Nescafe 2026"
    assert doc["metaTitle"] == "Win An Amazing Cosy Set-Up Thanks To NESCAFÉ®"
    assert "cosy set-up" in doc["metaDescription"].lower()


def test_extract_competition_json_finds_the_real_tiebreaker():
    doc = extract_competition_json(PAGE_HTML)

    assert doc["entryMechanic"] == "entryMultipleChoice"
    mc = doc["entryMultipleChoice"]
    assert mc["question"] == "Which of these books was written by Roald Dahl?"
    assert mc["answers"] == ["Matilda", "The Gruffalo", "The Railway Children"]
    assert mc["correctAnswer"] == "Matilda"


def test_extract_competition_json_finds_the_real_campaign_block():
    doc = extract_competition_json(PAGE_HTML)

    campaign = doc["campaign"]
    assert campaign["dataManagerId"] == 2587
    assert campaign["client"] == "Nescafe"
    assert campaign["startDate"] == "2026-09-30 17:00:00"
    assert campaign["endDate"] == "2026-10-29 23:59:00"
    assert campaign["terms_url"] == "https://campaign.smoothradio.com/terms-conditions/7761cbad-0881-4a78-9dd4-379dff2a"


def test_extract_competition_json_returns_none_for_unrelated_html():
    assert extract_competition_json("<html><body>not a competition page</body></html>") is None


def test_extract_competition_json_returns_none_for_empty_html():
    assert extract_competition_json("") is None


# --- _tandc_text() / _classify_free_paid() — against the real T&Cs fixture -


def test_tandc_text_strips_tags_and_extracts_real_body():
    text = _tandc_text(TERMS_HTML)

    assert "Nescafe" in text
    assert "<" not in text  # no raw tags left


def test_classify_free_paid_real_fixture_has_no_explicit_cost_language():
    # Confirmed live — this real T&Cs page states neither "free of charge" nor
    # "no purchase necessary" anywhere, despite the entry mechanism itself
    # plainly having no payment step. Must stay ambiguous, never guessed free.
    text = _tandc_text(TERMS_HTML)

    is_free, excerpt = _classify_free_paid(text)

    assert is_free is None
    assert "no explicit free/paid" in excerpt


def test_classify_free_paid_returns_true_on_an_explicit_free_phrase():
    is_free, excerpt = _classify_free_paid("Online entry is free of charge for all UK residents.")

    assert is_free is True
    assert "free of charge" in excerpt.lower()


def test_classify_free_paid_never_returns_false():
    # No real paid-signal pattern has been seen yet on this platform (see module
    # docstring) — even unrelated/empty text must come back None, not False.
    is_free, _excerpt = _classify_free_paid("This competition costs £1.50 to enter by SMS.")

    assert is_free is None


# --- parse_detail() — pure, against the real fixture doc ------------------


def test_parse_detail_real_competition():
    doc = extract_competition_json(PAGE_HTML)
    tandc_text = _tandc_text(TERMS_HTML)

    promo, channels = parse_detail(doc, SOURCE_URL, tandc_text)

    assert promo is not None
    assert promo.title == "Win An Amazing Cosy Set-Up Thanks To NESCAFÉ®"
    assert promo.station_name_raw == STATION_NAME == "Global Commercial"
    assert promo.network == STATION_NETWORK == "Global"
    assert promo.source_url == SOURCE_URL
    assert promo.discovered_via == DiscoveredVia.DIRECT
    assert promo.entry_deadline == date(2026, 10, 29)
    # No £ figure in the title (a physical prize bundle, not cash) — never
    # guessed from anywhere else, same "prefer None" posture as every other
    # adapter here.
    assert promo.prize_value_gbp is None

    assert len(channels) == 1
    channel = channels[0]
    assert channel.channel_type == EntryChannelType.WEB_FORM
    assert channel.channel_url_or_number == SOURCE_URL
    # Real fixture has no explicit free/paid language at all — see above.
    assert channel.is_free_route is None
    assert channel.cost_to_entrant_gbp is None
    assert channel.review_recommended is True


def test_parse_detail_prefers_meta_title_over_internal_sanity_title():
    doc = {"slug": "x", "title": "Internal Admin Label", "metaTitle": "Real Human-Facing Title", "campaign": {}}

    promo, _channels = parse_detail(doc, SOURCE_URL, "")

    assert promo.title == "Real Human-Facing Title"


def test_parse_detail_falls_back_to_title_when_meta_title_missing():
    doc = {"slug": "x", "title": "Only Title Present", "metaTitle": None, "campaign": {}}

    promo, _channels = parse_detail(doc, SOURCE_URL, "")

    assert promo.title == "Only Title Present"


def test_parse_detail_returns_none_promotion_when_no_title_at_all():
    doc = {"slug": "x", "title": None, "metaTitle": None, "campaign": {"endDate": "2026-10-29 23:59:00"}}

    promo, channels = parse_detail(doc, SOURCE_URL, "")

    assert promo is None
    assert channels == []


def test_parse_detail_returns_none_promotion_when_no_campaign_at_all():
    doc = {"slug": "x", "title": "A Title", "metaTitle": None, "campaign": None}

    promo, channels = parse_detail(doc, SOURCE_URL, "")

    assert promo is None
    assert channels == []


def test_parse_detail_missing_end_date_leaves_deadline_none():
    doc = {"slug": "x", "title": "A Title", "metaTitle": None, "campaign": {"endDate": None}}

    promo, _channels = parse_detail(doc, SOURCE_URL, "")

    assert promo is not None
    assert promo.entry_deadline is None


def test_parse_detail_extracts_prize_value_when_title_has_a_pound_figure():
    doc = {"slug": "x", "title": "Win £500 Cash", "metaTitle": None, "campaign": {"endDate": None}}

    promo, _channels = parse_detail(doc, SOURCE_URL, "")

    assert promo.prize_value_gbp == 500.0


# --- ingest() end-to-end, against a fake httpx.Client ----------------------


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://comp.smoothradio.com/")
            raise httpx.HTTPStatusError(
                "error", request=request, response=httpx.Response(self.status_code, request=request)
            )


class _FakeClient:
    """Maps URL -> canned HTML text, keyed loosely (substring match) — same
    technique as test_global_win.py's own _FakeClient, adapted for text responses
    rather than JSON. Used as a context manager, matching ingest()'s own
    `with httpx.Client(...) as client:` usage."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get(self, url, **kwargs):
        self.calls.append(url)
        for key, text in self.routes.items():
            if key in url:
                return _FakeResponse(text)
        raise AssertionError(f"no fake route for {url}")


def test_ingest_records_the_real_competition_via_a_fake_client(monkeypatch, tmp_path):
    import radiocomp.stations.global_commercial as gc_module

    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    fake_client = _FakeClient(
        {
            "comp.smoothradio.com/nescafe-2026/8": PAGE_HTML,
            "campaign.smoothradio.com/terms-conditions": TERMS_HTML,
        }
    )
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: fake_client)

    promos, channels = gc_module.ingest()

    assert len(promos) == 1
    assert promos[0].title == "Win An Amazing Cosy Set-Up Thanks To NESCAFÉ®"
    assert promos[0].station_name_raw == "Global Commercial"
    assert len(channels) == 1
    assert channels[0].promotion_id == promos[0].id
    # Both the competition page and its linked T&Cs page were actually fetched.
    assert any("nescafe-2026/8" in c for c in fake_client.calls)
    assert any("terms-conditions" in c for c in fake_client.calls)


def test_ingest_skips_a_page_with_no_embedded_competition_json(monkeypatch, tmp_path):
    import radiocomp.stations.global_commercial as gc_module

    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    fake_client = _FakeClient({"comp.smoothradio.com/nescafe-2026/8": "<html><body>gone</body></html>"})
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: fake_client)

    promos, channels = gc_module.ingest()

    assert promos == []
    assert channels == []


def test_ingest_is_idempotent_against_the_same_real_competition(monkeypatch, tmp_path):
    import radiocomp.stations.global_commercial as gc_module

    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    fake_client = _FakeClient(
        {
            "comp.smoothradio.com/nescafe-2026/8": PAGE_HTML,
            "campaign.smoothradio.com/terms-conditions": TERMS_HTML,
        }
    )
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: fake_client)

    first_promos, _ = gc_module.ingest()
    second_promos, _ = gc_module.ingest()

    assert len(first_promos) == 1
    assert len(second_promos) == 0  # already recorded — same dedup_hash
