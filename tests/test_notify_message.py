from __future__ import annotations

from datetime import date

from radiocomp.compliance.engine import ComplianceCheck
from radiocomp.models import DiscoveredVia, EntryChannel, EntryChannelType, Promotion
from radiocomp.notify.message import build_message_text, build_notification, build_reply_markup


def _promo(**overrides) -> Promotion:
    defaults = dict(
        station_name_raw="Radio X",
        title="Win a Car",
        discovered_via=DiscoveredVia.DIRECT,
        source_url="https://example.com/win-a-car",
        dedup_hash="hash1",
    )
    defaults.update(overrides)
    return Promotion(**defaults)


def _channel(**overrides) -> EntryChannel:
    # POST by default, not WEB_FORM — WEB_FORM is excluded by
    # select_approvable_channel (entry_execution/ handles it instead), so
    # build_notification() tests need a channel type that can actually
    # qualify. build_reply_markup() itself is channel-type-agnostic (the
    # exclusion lives one level up), so tests calling it directly are
    # unaffected either way.
    defaults = dict(promotion_id="p1", channel_type=EntryChannelType.POST)
    defaults.update(overrides)
    return EntryChannel(**defaults)


def _clean_check(promotion_id: str) -> ComplianceCheck:
    return ComplianceCheck(promotion_id=promotion_id, already_entered=False, shared_limit_network=None)


def test_message_includes_title_station_and_deadline():
    promo = _promo(entry_deadline=date(2026, 12, 25))
    text = build_message_text(promo, [], _clean_check(promo.id))
    assert "Win a Car" in text
    assert "Radio X" in text
    assert "2026-12-25" in text
    assert promo.source_url in text


def test_no_channels_says_so():
    promo = _promo()
    text = build_message_text(promo, [], _clean_check(promo.id))
    assert "no entry channels recorded yet" in text


def test_blocking_compliance_check_appends_warning():
    promo = _promo()
    check = ComplianceCheck(
        promotion_id=promo.id,
        already_entered=True,
        shared_limit_network=None,
    )
    text = build_message_text(promo, [], check)
    assert "⚠️" in text
    assert "already entered" in text.lower()


def test_reply_markup_none_when_no_approvable_channel():
    assert build_reply_markup("promo1", None) is None


def test_reply_markup_has_approve_and_skip_when_channel_qualifies():
    ch = _channel(id="chan1", is_free_route=True, review_recommended=False)
    markup = build_reply_markup("promo1", ch)
    buttons = markup["inline_keyboard"][0]
    assert len(buttons) == 2
    assert buttons[0]["text"] == "✅ Approve"
    assert buttons[1]["text"] == "⏭ Skip"
    assert buttons[0]["callback_data"] == "a:promo1:chan1"
    assert buttons[1]["callback_data"] == "s:promo1:chan1"


def test_build_notification_no_buttons_when_only_paid_channel():
    promo = _promo()
    paid = _channel(is_free_route=False, cost_to_entrant_gbp=2.50)
    text, markup = build_notification(promo, [paid], _clean_check(promo.id))
    assert "[PAID]" in text
    assert markup is None


def test_build_notification_has_buttons_when_free_channel_present():
    promo = _promo()
    free = _channel(is_free_route=True, review_recommended=False)
    text, markup = build_notification(promo, [free], _clean_check(promo.id))
    assert "[FREE]" in text
    assert markup is not None
