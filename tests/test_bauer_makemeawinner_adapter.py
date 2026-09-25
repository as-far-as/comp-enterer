"""
Tests against real captured API responses (tests/fixtures/
bauer_makemeawinner_*.json, captured live from api.winhappy.com on
2026-09-09) — same "test against something real, not mocked-up sample
data" convention as every other adapter here. No network/httpx mocking
needed for the pure functions (parse_campaign_item, extract_phone_channel,
extract_post_channel) since they take already-fetched data;
fetch_session_token()/fetch_listing()/fetch_campaign_info() (the only I/O
in this adapter) aren't unit-tested for the same reason talksport.py's/
radioexe.py's fetch() isn't — there's nothing to assert against without
hitting the real API.

Real data at capture time had zero free campaigns (matches the pattern
already found elsewhere in this project) — the free-classification path
is tested against a synthetic item, clearly marked as such below.

The phone/post channel extraction was added after a real gap was found
the hard way: the user manually entered a "paid" campaign for free via
its phone line, which this adapter hadn't recorded at all (see module
docstring) — the fixtures here were captured specifically to fix and
verify that.
"""

from __future__ import annotations

import json
from pathlib import Path

from radiocomp.models import EntryChannelType
from radiocomp.stations.bauer_makemeawinner import (
    STATION_NAME,
    STATION_NETWORK,
    _tandc_text,
    extract_phone_channel,
    extract_post_channel,
    parse_campaign_item,
)

FIXTURES = Path(__file__).parent / "fixtures"
LISTING_FIXTURE = FIXTURES / "bauer_makemeawinner_campaign_page_home.json"


def _real_campaign_items() -> list[dict]:
    data = json.loads(LISTING_FIXTURE.read_text())
    items = [item for group in data["groups"] for item in group["items"]]
    return [item for item in items if item.get("type") == "CAMPAIGN"]


def _real_tandc_text(tag: str) -> str:
    info = json.loads((FIXTURES / f"bauer_makemeawinner_campaign_info_{tag}.json").read_text())
    return _tandc_text(info)


def test_real_fixture_has_at_least_one_campaign_item():
    items = _real_campaign_items()
    assert len(items) > 0


def test_real_paid_campaign_classifies_confidently_paid_no_review_needed():
    items = _real_campaign_items()
    item = next(i for i in items if i["tag"] == "MAKEMEAWINNER")

    promo, channels = parse_campaign_item(item)

    assert promo.title == "Make Me A Winner - Win £500,000"
    assert promo.station_name_raw == STATION_NAME
    assert promo.network == STATION_NETWORK
    assert promo.prize_value_gbp == 500000.0
    assert promo.entry_deadline is not None
    assert promo.source_url == "https://makemeawinner.co.uk/campaign/MAKEMEAWINNER"

    web_form = channels[0]
    assert web_form.channel_type == EntryChannelType.WEB_FORM
    assert web_form.is_free_route is False
    assert web_form.cost_to_entrant_gbp is None
    # A genuine boolean straight from Bauer's own backend — confident
    # either way, never needs a human review flag the way every
    # regex-based classifier elsewhere in this codebase does.
    assert web_form.review_recommended is False


def test_all_real_current_campaigns_are_paid_not_free():
    # Documents the real state at fixture-capture time — real data
    # showed zero free campaigns, matching the pattern already found for
    # talkSPORT's widget. Not a design assumption; if this ever starts
    # failing because a real campaign IS free, that's good news, not a
    # broken test — update the fixture/assertion to match.
    items = _real_campaign_items()
    results = [parse_campaign_item(item) for item in items]
    assert all(channels[0].is_free_route is False for _, channels in results)


def test_synthetic_free_campaign_classifies_confidently_free():
    # Synthetic — no real free campaign exists in the fixture (see module
    # docstring). Shape matches the real schema exactly (same fields as
    # a real CAMPAIGN item), only is_free flipped to True.
    item = {
        "tag": "SYNTHETICFREEBIE",
        "title": "Win a Free Entry Giveaway",
        "start_date": 1788538200000,
        "end_date": 1789142400000,
        "type": "CAMPAIGN",
        "is_free": True,
    }

    promo, channels = parse_campaign_item(item)

    web_form = channels[0]
    assert web_form.is_free_route is True
    assert web_form.cost_to_entrant_gbp == 0.0
    assert web_form.review_recommended is False


def test_missing_is_free_field_stays_unclassified_never_guessed():
    item = {
        "tag": "UNKNOWNSHAPE",
        "title": "Win Something Unclear",
        "start_date": None,
        "end_date": None,
        "type": "CAMPAIGN",
        # is_free deliberately absent — simulates an API response shape
        # this adapter hasn't seen before.
    }

    promo, channels = parse_campaign_item(item)

    web_form = channels[0]
    assert web_form.is_free_route is None
    assert web_form.review_recommended is True


def test_real_phone_route_extracted_as_confidently_free_but_never_automatable():
    # MAKEMEAWINNER's real T&Cs: "PHONE Entrants can enter ... by calling
    # 0372 376 7519 ... Calls (from the UK) are charged at standard
    # network rate." — the exact route the user found manually before
    # this adapter recorded it at all.
    text = _real_tandc_text("MAKEMEAWINNER")
    channel = extract_phone_channel(text)

    assert channel is not None
    assert channel.channel_type == EntryChannelType.PHONE_ENTRY
    assert channel.is_free_route is True
    assert channel.cost_to_entrant_gbp == 0.0
    assert channel.review_recommended is False
    assert channel.channel_url_or_number == "0372 376 7519"


def test_real_post_route_extracted_as_free():
    # IPHONE17PRO's real T&Cs: "POST Entrants can also enter by sending
    # their name and mobile telephone number to MMAW BR7616, PO Box 8162,
    # Derby, DE1 9GU."
    text = _real_tandc_text("IPHONE17PRO")
    channel = extract_post_channel(text)

    assert channel is not None
    assert channel.channel_type == EntryChannelType.POST
    assert channel.is_free_route is True
    assert channel.review_recommended is False
    assert "PO Box 8162" in channel.channel_url_or_number


def test_real_post_route_with_the_alternate_phrasing_still_extracts():
    # LANDROVER's real T&Cs use a different opening sentence ("POST
    # Postal entries must be received...") than IPHONE17PRO's ("POST
    # Entrants can also enter...") before the actual PO Box address
    # appears later in the same section — found by spot-checking a
    # campaign that the first version of this regex incorrectly returned
    # nothing for.
    text = _real_tandc_text("LANDROVER")
    channel = extract_post_channel(text)

    assert channel is not None
    assert channel.is_free_route is True
    assert "PO Box 8162" in channel.channel_url_or_number


def test_campaign_with_no_extractable_phone_or_post_route_returns_none():
    # HOLIDAYORCASH's real campaign/info response turned out to be a
    # redirect wrapper (type: EXTERNAL, body is just a "<p>TERMS</p>"
    # placeholder — the real T&Cs live at its redirect_url instead) —
    # a genuinely different reason than "no phone/post route exists," but
    # the correct, conservative behaviour is identical either way: find
    # nothing, extract nothing, never guess.
    text = _real_tandc_text("HOLIDAYORCASH")

    assert extract_phone_channel(text) is None
    assert extract_post_channel(text) is None


def test_phone_and_post_channels_both_attach_to_the_same_promotion_when_both_present():
    item = {
        "tag": "MAKEMEAWINNER",
        "title": "Make Me A Winner - Win £500,000",
        "start_date": 1787933400000,
        "end_date": 1789142400000,
        "type": "CAMPAIGN",
        "is_free": False,
    }
    # Synthetic combined text — real fixtures each only have one of the
    # two routes; this proves the merge logic itself (both get appended)
    # independent of what any single real campaign happens to offer.
    text = (
        "PHONE Entrants can enter by calling 0372 376 7519. Calls (from the UK) are charged at standard network rate. "
        "POST Entrants can also enter by sending their name to MMAW BR7616, PO Box 8162, Derby, DE1 9GU."
    )

    promo, channels = parse_campaign_item(item, tandc_text=text)

    types = {c.channel_type for c in channels}
    assert types == {EntryChannelType.WEB_FORM, EntryChannelType.PHONE_ENTRY, EntryChannelType.POST}
    assert all(c.promotion_id == "" for c in channels)  # set by ingest(), not parse_campaign_item()
