"""
Tests against real captured API responses (tests/fixtures/heart_global_*.json,
captured live from winplus.heart.co.uk's own unauthenticated JSON endpoints
on 2026-09-23) — same "test against something real, not mocked-up sample
data" convention as every other adapter here.

Fixtures:
- heart_global_init.json — winplus.heart.co.uk's own /data/init.json, used
  to resolve "heart" -> its real numeric brand id (2).
- heart_global_competitions_list.json — /data/competitions/list.json, every
  competition currently in Global's system, each tagged with which brands
  show it.
- heart_global_competition_details_13201.json — "Win £10,000", a real paid
  competition whose own T&Cs describe a free phone-entry alternative
  ("Free Entry Route by phone call... call 03434150054... charged at your
  standard network rate only").
- heart_global_competition_details_13270.json — "Win a Ninja Double Stack
  Air Fryer", a real paid competition whose own T&Cs describe a free postal
  alternative instead ("Free Entry via Post... PO Box 8669, Derby,
  DE1 9SR") — confirming phone and post are mutually exclusive real
  alternatives on this platform, never both on the same competition.
- heart_global_competition_details_13666.json — "Win Two Tickets to See
  Westlife", a real competition with competitionEntryType="free" — already
  free online, so (confirmed against the real fixture) no phone/post
  alternative route is described at all.
- global_win_competition_details_13771_non_heart_brand.json — "Win Two
  Tickets to See Manic Street Preachers and Suede", a real competition
  tagged `brands: [67, 6]` (Global Player + Radio X only — Heart, brand id
  2, is NOT among them), captured live 2026-09-25 specifically to prove
  this module now records a competition regardless of which brand(s) it's
  tagged with, rather than filtering to Heart's brand id (see module
  docstring's "Generalised" note).

No live network call is ever made in these tests. fetch_brand_id()/
fetch_competition_list()/fetch_competition_details() take an httpx.Client,
so they're exercised here via a fake client whose .get() returns the saved
fixture JSON, same technique as bauer_makemeawinner.py's own tests use for
its per-item T&Cs calls, adapted to a client-argument style since this
adapter's fetch functions take a client rather than calling httpx module
functions directly (matching bauer_makemeawinner.py's own fetch_* shape,
not wayin.py's bare httpx.get() shape).

login()'s real Gigya accounts.login call is never exercised against the
live network here, and no real credentials are ever set — only the
token-derivation math (a pure function) and login()'s own request
construction (via a mocked httpx.Client, still no real network call) and
error-handling are tested.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from radiocomp import config
from radiocomp.models import EntryChannelType
from radiocomp.stations.global_win import (
    STATION_NAME,
    STATION_NETWORK,
    _derive_bff_token,
    extract_phone_channel,
    extract_post_channel,
    fetch_brand_id,
    fetch_competition_details,
    fetch_competition_list,
    login,
    parse_detail,
)

FIXTURES = Path(__file__).parent / "fixtures"

INIT = json.loads((FIXTURES / "heart_global_init.json").read_text())
LIST = json.loads((FIXTURES / "heart_global_competitions_list.json").read_text())
DETAILS_PHONE = json.loads((FIXTURES / "heart_global_competition_details_13201.json").read_text())  # Win £10,000
DETAILS_POST = json.loads(
    (FIXTURES / "heart_global_competition_details_13270.json").read_text()
)  # Ninja Air Fryer
DETAILS_FREE = json.loads((FIXTURES / "heart_global_competition_details_13666.json").read_text())  # Westlife
DETAILS_NON_HEART_BRAND = json.loads(
    (FIXTURES / "global_win_competition_details_13771_non_heart_brand.json").read_text()
)  # Manic Street Preachers/Suede — brands: [67, 6], no Heart (id 2)


class _FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://winplus.heart.co.uk/")
            raise httpx.HTTPStatusError("error", request=request, response=httpx.Response(self.status_code, request=request))


class _FakeClient:
    """Maps URL -> canned JSON response, mimicking the one real winplus.heart.co.uk
    endpoint each test needs, keyed loosely (substring match) so the same fake
    works whether the adapter calls init.json/list.json/details.json."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        for key, data in self.routes.items():
            if key in url:
                return _FakeResponse(data)
        raise AssertionError(f"no fake route for {url}")

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        for key, data in self.routes.items():
            if key in url:
                return _FakeResponse(data)
        raise AssertionError(f"no fake route for {url}")


# --- fetch_* against a fake client (no real network call) -----------------


def test_fetch_brand_id_resolves_heart_from_real_init_fixture():
    client = _FakeClient({"init.json": INIT})

    brand_id = fetch_brand_id(client)

    assert brand_id == 2  # confirmed live 2026-09-23 — see module docstring


def test_fetch_brand_id_returns_none_when_brand_not_present():
    client = _FakeClient({"init.json": {"brands": {}}})

    assert fetch_brand_id(client) is None


def test_fetch_competition_list_returns_real_fixture_list():
    client = _FakeClient({"list.json": LIST})

    listing = fetch_competition_list(client)

    assert listing == LIST
    assert len(listing) > 0


def test_fetch_competition_details_returns_real_fixture():
    client = _FakeClient({"details.json": DETAILS_PHONE})

    details = fetch_competition_details(client, 13201)

    assert details == DETAILS_PHONE


# --- real fixture data shape sanity ----------------------------------------


def test_real_list_fixture_has_heart_relevant_items_matching_the_resolved_brand_id():
    # Heart's own homepage only ever showed items whose `brands` array
    # contains 2 — confirmed by diffing against the real rendered homepage
    # at capture time (see module docstring). This just re-checks the
    # membership test the adapter's own ingest() relies on still holds
    # against the saved fixture.
    heart_items = [item for item in LIST if 2 in (item.get("brands") or [])]
    assert len(heart_items) > 0
    assert any(item["id"] == 13201 for item in heart_items)


# --- parse_detail() — pure, against real fixtures --------------------------


def test_parse_detail_real_paid_competition_with_phone_route():
    promo, channels = parse_detail(DETAILS_PHONE)

    assert promo is not None
    assert promo.title == "Win £10,000"
    assert promo.station_name_raw == STATION_NAME == "Global WIN"
    assert promo.network == STATION_NETWORK == "Global"
    assert promo.source_url == "https://winplus.heart.co.uk/competition/13201/win-pound10000"
    assert promo.discovered_via.value == "direct"
    assert promo.entry_deadline is not None
    assert promo.entry_deadline.isoformat() == "2026-09-28"  # real dateStop: 2026-09-28T14:00:00.000Z
    assert promo.prize_value_gbp == 10000.0  # title-only extraction, "Win £10,000"

    assert len(channels) == 2
    web_form = next(c for c in channels if c.channel_type == EntryChannelType.WEB_FORM)
    assert web_form.is_free_route is False  # real competitionEntryType == "paid"
    assert web_form.cost_to_entrant_gbp is None
    assert web_form.review_recommended is False  # a genuine field, not a guess — confident either way

    phone = next(c for c in channels if c.channel_type == EntryChannelType.PHONE_ENTRY)
    assert phone.is_free_route is True
    assert phone.cost_to_entrant_gbp == 0.0
    assert phone.review_recommended is False
    assert phone.channel_url_or_number == "03434150054"  # real number, standard rate, from the real T&Cs


def test_parse_detail_real_paid_competition_with_post_route_instead_of_phone():
    promo, channels = parse_detail(DETAILS_POST)

    assert promo is not None
    assert promo.title == "Win a Ninja Double Stack Air Fryer"
    assert promo.entry_deadline is not None
    assert promo.entry_deadline.isoformat() == "2026-09-27"
    # No single £ figure in this title (a physical prize, not cash) —
    # never guessed from anywhere else, same "prefer None" posture as
    # every other adapter here.
    assert promo.prize_value_gbp is None

    assert len(channels) == 2
    web_form = next(c for c in channels if c.channel_type == EntryChannelType.WEB_FORM)
    assert web_form.is_free_route is False

    post = next(c for c in channels if c.channel_type == EntryChannelType.POST)
    assert post.is_free_route is True
    assert post.cost_to_entrant_gbp == 0.0
    assert post.review_recommended is False
    assert post.channel_url_or_number == "PO Box 8669, Derby, DE1 9SR"

    # Never both on the same real competition (see module docstring) —
    # confirms this one really only carries the post alternative.
    assert not any(c.channel_type == EntryChannelType.PHONE_ENTRY for c in channels)


def test_parse_detail_real_free_competition_has_no_phone_or_post_alternative():
    promo, channels = parse_detail(DETAILS_FREE)

    assert promo is not None
    assert promo.title == "Win Two Tickets to See Westlife"
    assert promo.prize_value_gbp is None  # no £ figure in the title

    assert len(channels) == 1  # web_form only — already free online, no alternative route needed
    web_form = channels[0]
    assert web_form.channel_type == EntryChannelType.WEB_FORM
    assert web_form.is_free_route is True  # real competitionEntryType == "free"
    assert web_form.cost_to_entrant_gbp == 0.0
    assert web_form.review_recommended is False


def test_parse_detail_unrecognised_entry_type_stays_ambiguous_never_guessed():
    detail = dict(DETAILS_PHONE)
    detail["competitionEntryType"] = "something-new-and-unseen"

    promo, channels = parse_detail(detail)

    web_form = next(c for c in channels if c.channel_type == EntryChannelType.WEB_FORM)
    assert web_form.is_free_route is None
    assert web_form.cost_to_entrant_gbp is None
    assert web_form.review_recommended is True


def test_parse_detail_missing_id_slug_or_title_returns_none_promotion_not_an_exception():
    promo, channels = parse_detail({"id": None, "slug": "x", "title": "Win Something"})

    assert promo is None
    assert channels == []


def test_parse_detail_missing_date_stop_leaves_deadline_none():
    detail = dict(DETAILS_FREE)
    detail["dateStop"] = None

    promo, _channels = parse_detail(detail)

    assert promo is not None
    assert promo.entry_deadline is None


# --- extract_phone_channel / extract_post_channel — pure -------------------


def test_extract_phone_channel_returns_none_when_no_phone_route_present():
    from radiocomp.stations.global_win import _tandc_text

    text = _tandc_text(DETAILS_POST)  # this real competition only has a post route

    assert extract_phone_channel(text) is None


def test_extract_post_channel_returns_none_when_no_post_route_present():
    from radiocomp.stations.global_win import _tandc_text

    text = _tandc_text(DETAILS_PHONE)  # this real competition only has a phone route

    assert extract_post_channel(text) is None


def test_extract_phone_channel_without_standard_rate_language_stays_review_recommended():
    text = "Free Entry Route by phone call. To enter, call 03001234567 from a valid UK phone."
    # Deliberately omits "standard network rate" — never seen on a real
    # fixture, but the extractor must not assume standard rate just
    # because a phone route exists.

    channel = extract_phone_channel(text)

    assert channel is not None
    assert channel.is_free_route is None
    assert channel.review_recommended is True
    assert channel.channel_url_or_number == "03001234567"


# --- ingest() end-to-end, brand-agnostic behaviour ---------------------


def test_ingest_still_proceeds_when_brand_id_cannot_be_resolved(monkeypatch, tmp_path):
    """fetch_brand_id() is informational only now (see module docstring's
    "Generalised" note) — a failure to resolve it must NOT stop ingest()
    from processing the full listing, unlike the old Heart-only adapter
    where a missing brand id meant "can't safely proceed"."""
    import radiocomp.stations.global_win as global_win_module

    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)  # isolate from real project data/
    monkeypatch.setattr(global_win_module, "fetch_brand_id", lambda client: None)
    monkeypatch.setattr(global_win_module, "fetch_competition_list", lambda client: [DETAILS_FREE])
    monkeypatch.setattr(global_win_module, "fetch_competition_details", lambda client, comp_id: DETAILS_FREE)

    promos, channels = global_win_module.ingest()

    assert len(promos) == 1
    assert promos[0].title == "Win Two Tickets to See Westlife"


def test_ingest_records_a_competition_not_tagged_with_the_heart_brand_at_all(monkeypatch, tmp_path):
    """The real point of this generalisation: a competition whose own
    `brands` array never includes Heart's id (2) at all — see
    DETAILS_NON_HEART_BRAND, brands: [67, 6] — must still be recorded.
    The old, Heart-only adapter would have silently dropped this one."""
    import radiocomp.stations.global_win as global_win_module

    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    monkeypatch.setattr(global_win_module, "fetch_brand_id", lambda client: 2)  # Heart, as normal
    monkeypatch.setattr(global_win_module, "fetch_competition_list", lambda client: [DETAILS_NON_HEART_BRAND])
    monkeypatch.setattr(
        global_win_module, "fetch_competition_details", lambda client, comp_id: DETAILS_NON_HEART_BRAND
    )

    promos, channels = global_win_module.ingest()

    assert len(promos) == 1
    assert promos[0].title == "Win Two Tickets to See Manic Street Preachers and Suede"
    assert promos[0].station_name_raw == "Global WIN"
    assert 2 not in DETAILS_NON_HEART_BRAND["brands"]  # sanity: really isn't Heart-tagged


def test_ingest_skips_hidden_competitions_regardless_of_brand(monkeypatch, tmp_path):
    import radiocomp.stations.global_win as global_win_module

    hidden = dict(DETAILS_FREE)
    hidden["hidden"] = True

    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    monkeypatch.setattr(global_win_module, "fetch_brand_id", lambda client: 2)
    monkeypatch.setattr(global_win_module, "fetch_competition_list", lambda client: [hidden])
    monkeypatch.setattr(
        global_win_module,
        "fetch_competition_details",
        lambda client, comp_id: (_ for _ in ()).throw(AssertionError("hidden items should never reach details.json")),
    )

    promos, channels = global_win_module.ingest()

    assert promos == []
    assert channels == []


# --- login() — never a real network call ------------------------------


def test_login_raises_runtime_error_when_credentials_unset():
    assert config.GLOBAL_PLAYER_EMAIL == ""
    assert config.GLOBAL_PLAYER_PASSWORD == ""

    with pytest.raises(RuntimeError, match="GLOBAL_PLAYER_EMAIL"):
        login(client=None)  # never reaches the client — raises before any network call


def test_login_succeeds_with_mocked_successful_gigya_response(monkeypatch):
    monkeypatch.setattr(config, "GLOBAL_PLAYER_EMAIL", "fake-test-user@example.com")
    monkeypatch.setattr(config, "GLOBAL_PLAYER_PASSWORD", "fake-test-password")

    fake_gigya_response = {
        "errorCode": 0,
        "UID": "fake-uid-1234",
        "UIDSignature": "fake-signature==",
        "signatureTimestamp": "1790000000",
    }
    client = _FakeClient({"accounts.login": fake_gigya_response})

    token = login(client)

    assert isinstance(token, str) and token  # a non-empty base64 string
    import base64
    import json as json_mod

    decoded = json_mod.loads(base64.b64decode(token))
    assert decoded == {"gigyaUID": "fake-uid-1234", "timestamp": "1790000000", "signature": "fake-signature=="}


def test_login_raises_runtime_error_on_nonzero_gigya_error_code(monkeypatch):
    monkeypatch.setattr(config, "GLOBAL_PLAYER_EMAIL", "fake-test-user@example.com")
    monkeypatch.setattr(config, "GLOBAL_PLAYER_PASSWORD", "wrong-fake-password")

    fake_gigya_response = {"errorCode": 403042, "errorMessage": "Invalid loginID or password."}
    client = _FakeClient({"accounts.login": fake_gigya_response})

    with pytest.raises(RuntimeError, match="Gigya login failed"):
        login(client)


def test_login_raises_runtime_error_when_success_response_missing_expected_fields(monkeypatch):
    monkeypatch.setattr(config, "GLOBAL_PLAYER_EMAIL", "fake-test-user@example.com")
    monkeypatch.setattr(config, "GLOBAL_PLAYER_PASSWORD", "fake-test-password")

    # errorCode 0 but a response shape this adapter has never actually
    # seen for real (recon was passive — see module docstring) — must
    # fail loudly, never guess a token out of an incomplete response.
    fake_gigya_response = {"errorCode": 0}
    client = _FakeClient({"accounts.login": fake_gigya_response})

    with pytest.raises(RuntimeError, match="missing expected"):
        login(client)


# --- token derivation — pure math, obviously-fake sample values --------


def test_derive_bff_token_shape():
    token = _derive_bff_token("fake-uid", "fake-signature==", "1790000000")

    import base64
    import json as json_mod

    decoded = json_mod.loads(base64.b64decode(token))
    assert decoded == {"gigyaUID": "fake-uid", "timestamp": "1790000000", "signature": "fake-signature=="}
