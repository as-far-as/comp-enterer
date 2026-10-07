"""
The Instagram daily digest (notify/instagram_digest.py) and its webhook
flows (Entered → comment-count range, Needs tags) — against real
LocalJsonRepository storage (tests/conftest.py), with only the outbound
Telegram calls faked.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from radiocomp import config
from radiocomp.models import (
    DigestRecord,
    DiscoveredVia,
    EntryChannel,
    EntryChannelType,
    EntryRecord,
    EntryStatus,
    Promotion,
)
from radiocomp.notify import instagram_digest
from radiocomp.notify.callback_data import build_callback_data
from radiocomp.storage.base import get_repository
from radiocomp.webhook import handlers

TODAY = date(2026, 10, 8)


def _promo(title, deadline=TODAY + timedelta(days=3), promoter="Shop(IG)", url=None):
    return Promotion(
        station_name_raw=promoter,
        title=title,
        entry_deadline=deadline,
        discovered_via=DiscoveredVia.AGGREGATOR,
        source_url=url or f"https://www.instagram.com/p/{title.replace(' ', '')}/",
        dedup_hash=title,
    )


def _channel(promo):
    return EntryChannel(promotion_id=promo.id, channel_type=EntryChannelType.INSTAGRAM, review_recommended=True)


def _select(promos, entries=(), digests=(), cap=5):
    return [p.title for p, _ in instagram_digest.select_suggestions(promos, [_channel(p) for p in promos], entries, digests, TODAY, cap)]


def test_soonest_closing_first_unknown_deadlines_last_and_capped():
    promos = [
        _promo("Later", TODAY + timedelta(days=9)),
        _promo("Undated", None),
        _promo("Soonest", TODAY),
        _promo("Middle", TODAY + timedelta(days=4)),
    ]
    assert _select(promos) == ["Soonest", "Middle", "Later", "Undated"]
    assert _select(promos, cap=2) == ["Soonest", "Middle"]


def test_excludes_closed_answered_already_suggested_and_non_instagram_links():
    closed = _promo("Closed", TODAY - timedelta(days=1))
    answered = _promo("Answered")
    suggested = _promo("Suggested")
    facebook = _promo("Facebook", url="https://www.facebook.com/shop/posts/123")
    fresh = _promo("Fresh")
    entries = [EntryRecord(promotion_id=answered.id, channel_type=EntryChannelType.INSTAGRAM, status=EntryStatus.SKIPPED)]
    digests = [DigestRecord(sent_on=TODAY - timedelta(days=1), promotion_ids=[suggested.id])]

    assert _select([closed, answered, suggested, facebook, fresh], entries, digests) == ["Fresh"]


def test_promoters_previously_marked_needs_tags_go_last():
    old = _promo("Old tag one", TODAY - timedelta(days=5), promoter="Taggy(IG)")
    taggy_new = _promo("Taggy new", TODAY)
    taggy_new.station_name_raw = "Taggy(IG)"
    other = _promo("Other", TODAY + timedelta(days=6))
    entries = [
        EntryRecord(promotion_id=old.id, channel_type=EntryChannelType.INSTAGRAM, status=EntryStatus.SKIPPED, skip_reason="needs_tags")
    ]
    assert _select([old, taggy_new, other], entries) == ["Other", "Taggy new"]


def test_draws_due_reminds_for_entered_giveaways_one_to_three_days_after_closing():
    entered_yesterday = _promo("A", TODAY - timedelta(days=1))
    entered_last_week = _promo("B", TODAY - timedelta(days=7))
    skipped_yesterday = _promo("C", TODAY - timedelta(days=1))
    entries = [
        EntryRecord(promotion_id=entered_yesterday.id, channel_type=EntryChannelType.INSTAGRAM, status=EntryStatus.SUBMITTED),
        EntryRecord(promotion_id=entered_last_week.id, channel_type=EntryChannelType.INSTAGRAM, status=EntryStatus.SUBMITTED),
        EntryRecord(promotion_id=skipped_yesterday.id, channel_type=EntryChannelType.INSTAGRAM, status=EntryStatus.SKIPPED),
    ]
    due = instagram_digest.draws_due([entered_yesterday, entered_last_week, skipped_yesterday], entries, TODAY)
    assert [p.title for p in due] == ["A"]

    header = instagram_digest.build_header(0, due)
    assert "Message Requests" in header and "A (Shop)" in header and "never asks you to pay" in header


def _configure_telegram(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "chat")
    sent = []
    monkeypatch.setattr(
        instagram_digest.telegram_client, "send_message", lambda chat_id, text, reply_markup=None: sent.append((text, reply_markup))
    )
    return sent


def _store(promos):
    for p in promos:
        get_repository("promotions", Promotion).add(p)
        get_repository("entry_channels", EntryChannel).add(_channel(p))


def test_send_daily_digest_sends_once_per_day_and_not_before_the_hour(monkeypatch):
    sent = _configure_telegram(monkeypatch)
    _store([_promo(f"Giveaway {i}") for i in range(7)])
    morning = datetime(2026, 10, 8, instagram_digest.DIGEST_HOUR_UTC)

    assert instagram_digest.send_daily_digest(now=morning - timedelta(hours=1)) == 0
    assert sent == []

    assert instagram_digest.send_daily_digest(now=morning) == 5
    assert len(sent) == 6  # header + 5 suggestions
    assert sent[0][0].startswith("📸 Instagram giveaways today: 5")

    assert instagram_digest.send_daily_digest(now=morning + timedelta(hours=1)) == 0
    assert len(sent) == 6

    # Next day: only the 2 never suggested remain.
    assert instagram_digest.send_daily_digest(now=morning + timedelta(days=1)) == 2


def _fake_handler_telegram(monkeypatch):
    acked, edited = [], []
    monkeypatch.setattr(handlers.telegram_client, "answer_callback_query", lambda cbq_id, text=None: acked.append(text))
    monkeypatch.setattr(
        handlers.telegram_client,
        "edit_message_text",
        lambda chat_id, message_id, text, reply_markup=None: edited.append((text, reply_markup)),
    )
    return acked, edited


def _tap(data, text="Giveaway"):
    handlers.handle_callback_query(
        {"id": "cb", "data": data, "message": {"chat": {"id": 1}, "message_id": 2, "text": text}}
    )


def test_entered_records_submitted_then_asks_for_comment_count(monkeypatch):
    acked, edited = _fake_handler_telegram(monkeypatch)
    promo = _promo("Hamper")
    channel = _channel(promo)
    get_repository("promotions", Promotion).add(promo)
    get_repository("entry_channels", EntryChannel).add(channel)

    _tap(build_callback_data("e", promo.id, channel.id))

    [record] = get_repository("entry_records", EntryRecord).list()
    assert record.status == EntryStatus.SUBMITTED
    assert record.submitted_at is not None
    text, markup = edited[-1]
    assert "how many comments" in text
    bucket_buttons = [b for row in markup["inline_keyboard"] for b in row]
    assert [b["text"] for b in bucket_buttons] == ["<50", "50-200", "200-1000", "1000+", "not checked"]

    _tap(bucket_buttons[1]["callback_data"], text)
    assert get_repository("entry_records", EntryRecord).get(record.id).observed_comment_bucket == "50-200"
    assert edited[-1][1] == {"inline_keyboard": []}

    # A second tap on a stale button doesn't overwrite the first answer.
    _tap(bucket_buttons[3]["callback_data"], text)
    assert get_repository("entry_records", EntryRecord).get(record.id).observed_comment_bucket == "50-200"


def test_needs_tags_records_a_skip_with_reason_and_repeat_taps_are_ignored(monkeypatch):
    acked, edited = _fake_handler_telegram(monkeypatch)
    promo = _promo("Tag three friends")
    channel = _channel(promo)
    get_repository("promotions", Promotion).add(promo)
    get_repository("entry_channels", EntryChannel).add(channel)

    _tap(build_callback_data("t", promo.id, channel.id))
    _tap(build_callback_data("e", promo.id, channel.id))

    [record] = get_repository("entry_records", EntryRecord).list()
    assert record.status == EntryStatus.SKIPPED
    assert record.skip_reason == "needs_tags"
    assert acked[-1] == "Already recorded"
