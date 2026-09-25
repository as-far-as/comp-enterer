from __future__ import annotations

from datetime import datetime

from radiocomp.entry_execution.eligibility import find_draftable_channels, find_submittable_entries
from radiocomp.models import (
    DiscoveredVia,
    EntryChannel,
    EntryChannelType,
    EntryRecord,
    EntryStatus,
    Promotion,
)
from radiocomp.dedup import promotion_dedup_hash


def _promo(**overrides) -> Promotion:
    defaults = dict(
        station_name_raw="Radio X",
        title="Win a Car",
        discovered_via=DiscoveredVia.DIRECT,
        source_url="https://example.com/win-a-car",
        dedup_hash=promotion_dedup_hash("Radio X", overrides.get("title", "Win a Car"), None),
    )
    defaults.update(overrides)
    return Promotion(**defaults)


def _channel(promo_id: str, **overrides) -> EntryChannel:
    defaults = dict(promotion_id=promo_id, channel_type=EntryChannelType.WEB_FORM)
    defaults.update(overrides)
    return EntryChannel(**defaults)


def test_clean_web_form_channel_is_draftable():
    promo = _promo()
    channel = _channel(promo.id, is_free_route=True, review_recommended=False)
    result = find_draftable_channels([promo], [channel], [])
    assert result == [(promo, channel)]


def test_the_exact_qualifying_shape_is_never_draftable_for_post_or_phone_entry():
    # This is the direct regression test for the hard-coded channel-type
    # filter: real data has shown POST and PHONE_ENTRY channels with this
    # identical "qualifying" shape (is_free_route=True, review_recommended=
    # False) — both are explicitly non-automatable (no phone automation,
    # ever; nothing here can post a letter), and must never be drafted
    # regardless of how free/confident they look.
    promo = _promo()
    post = _channel(promo.id, channel_type=EntryChannelType.POST, is_free_route=True, review_recommended=False)
    phone = _channel(promo.id, channel_type=EntryChannelType.PHONE_ENTRY, is_free_route=True, review_recommended=False)
    assert find_draftable_channels([promo], [post, phone], []) == []


def test_review_recommended_web_form_is_not_draftable():
    promo = _promo()
    channel = _channel(promo.id, is_free_route=True, review_recommended=True)
    assert find_draftable_channels([promo], [channel], []) == []


def test_paid_web_form_is_not_draftable():
    promo = _promo()
    channel = _channel(promo.id, is_free_route=False, cost_to_entrant_gbp=2.50)
    assert find_draftable_channels([promo], [channel], []) == []


def test_already_has_a_record_is_not_draftable_again():
    promo = _promo()
    channel = _channel(promo.id, is_free_route=True, review_recommended=False)
    existing = EntryRecord(
        promotion_id=promo.id, channel_type=channel.channel_type, channel_id=channel.id, status=EntryStatus.DRAFTED
    )
    assert find_draftable_channels([promo], [channel], [existing]) == []


def test_submittable_entries_requires_approved_web_form_not_yet_submitted():
    approved_web_form = EntryRecord(
        promotion_id="p1", channel_type=EntryChannelType.WEB_FORM, channel_id="c1", status=EntryStatus.APPROVED
    )
    already_submitted = EntryRecord(
        promotion_id="p2",
        channel_type=EntryChannelType.WEB_FORM,
        channel_id="c2",
        status=EntryStatus.APPROVED,
        submitted_at=datetime.utcnow(),
    )
    approved_post = EntryRecord(
        promotion_id="p3", channel_type=EntryChannelType.POST, channel_id="c3", status=EntryStatus.APPROVED
    )
    drafted_web_form = EntryRecord(
        promotion_id="p4", channel_type=EntryChannelType.WEB_FORM, channel_id="c4", status=EntryStatus.DRAFTED
    )

    result = find_submittable_entries([approved_web_form, already_submitted, approved_post, drafted_web_form])
    assert result == [approved_web_form]
