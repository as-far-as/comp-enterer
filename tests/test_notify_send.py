"""
notify_new_promotions() wiring — the actual Telegram HTTP call
(telegram_client.send_message) is faked here; only the orchestration
(no-op when unconfigured, per-promotion isolation, what gets passed to
send_message) is under test. Real delivery is verified live, same
convention as every other network-touching module in this codebase.
"""

from __future__ import annotations

from datetime import date

from radiocomp import config
from radiocomp.models import DiscoveredVia, EntryChannel, Promotion
from radiocomp.notify import send as notify_send
from radiocomp.storage.base import get_repository


def _promo(**overrides) -> Promotion:
    defaults = dict(
        station_name_raw="Radio X",
        title="Win a Car",
        discovered_via=DiscoveredVia.DIRECT,
        source_url="https://example.com/win-a-car",
        dedup_hash=f"hash-{overrides.get('title', 'default')}",
    )
    defaults.update(overrides)
    return Promotion(**defaults)


def _use_local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)


def test_noop_when_bot_token_unset(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "12345")

    calls = []
    monkeypatch.setattr(notify_send.telegram_client, "send_message", lambda *a, **k: calls.append((a, k)))

    notify_send.notify_new_promotions([_promo()])
    assert calls == []


def test_noop_when_no_new_promotions(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "12345")

    calls = []
    monkeypatch.setattr(notify_send.telegram_client, "send_message", lambda *a, **k: calls.append((a, k)))

    notify_send.notify_new_promotions([])
    assert calls == []


def test_sends_one_message_per_promotion(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "12345")

    promo_repo = get_repository("promotions", Promotion)
    p1, p2 = _promo(title="Win a Car"), _promo(title="Win a Holiday")
    promo_repo.add(p1)
    promo_repo.add(p2)

    calls = []
    monkeypatch.setattr(notify_send.telegram_client, "send_message", lambda *a, **k: calls.append(a))

    notify_send.notify_new_promotions([p1, p2])

    assert len(calls) == 2
    assert calls[0][0] == "12345"  # chat_id is always the first positional arg


def test_one_promotions_send_failure_does_not_stop_the_rest(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "12345")

    promo_repo = get_repository("promotions", Promotion)
    p1, p2 = _promo(title="Broken One"), _promo(title="Fine One")
    promo_repo.add(p1)
    promo_repo.add(p2)

    sent_titles = []

    def fake_send(chat_id, text, reply_markup=None):
        if "Broken" in text:
            raise RuntimeError("simulated Telegram API failure")
        sent_titles.append(text)

    monkeypatch.setattr(notify_send.telegram_client, "send_message", fake_send)

    notify_send.notify_new_promotions([p1, p2])
    assert len(sent_titles) == 1
    assert "Fine One" in sent_titles[0]


# --- recurring series: notify once, not once per occurrence ------------


def test_recurring_series_discovered_all_at_once_only_notifies_the_earliest(monkeypatch, tmp_path):
    # Real scenario, 2026-09-28: a first-ever discovery run found 4 days
    # of "Capital's Bong Game 2026" (same recurrence_series_id, different
    # entry_deadline) simultaneously — only the earliest-deadline one
    # should ever get a Telegram message.
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "12345")

    promo_repo = get_repository("promotions", Promotion)
    rounds = [
        _promo(title="Capital's Bong Game 2026", recurrence_series_id="11497", entry_deadline=d)
        for d in (date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2))
    ]
    for r in rounds:
        promo_repo.add(r)

    calls = []
    monkeypatch.setattr(notify_send.telegram_client, "send_message", lambda *a, **k: calls.append(a))

    notify_send.notify_new_promotions(rounds)

    assert len(calls) == 1
    assert "2026-09-29" in calls[0][1]  # the earliest round's own deadline, in its message text


def test_recurring_series_later_occurrence_is_skipped_when_an_earlier_one_already_exists(monkeypatch, tmp_path):
    # The realistic ongoing case: an earlier round was already stored (and
    # presumably already notified) in a previous run; today's new round
    # for the same series must not fire a second message.
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "12345")

    promo_repo = get_repository("promotions", Promotion)
    already_known = _promo(
        title="Capital's Bong Game 2026", recurrence_series_id="11497", entry_deadline=date(2026, 9, 29)
    )
    promo_repo.add(already_known)

    todays_round = _promo(
        title="Capital's Bong Game 2026", recurrence_series_id="11497", entry_deadline=date(2026, 9, 30)
    )
    promo_repo.add(todays_round)

    calls = []
    monkeypatch.setattr(notify_send.telegram_client, "send_message", lambda *a, **k: calls.append(a))

    notify_send.notify_new_promotions([todays_round])

    assert calls == []


def test_non_recurring_promotions_are_unaffected_by_series_logic(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "12345")

    promo_repo = get_repository("promotions", Promotion)
    p1, p2 = _promo(title="Win a Car"), _promo(title="Win a Holiday")
    promo_repo.add(p1)
    promo_repo.add(p2)

    calls = []
    monkeypatch.setattr(notify_send.telegram_client, "send_message", lambda *a, **k: calls.append(a))

    notify_send.notify_new_promotions([p1, p2])

    assert len(calls) == 2
