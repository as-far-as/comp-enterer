"""
notify_new_promotions() wiring — the actual Telegram HTTP call
(telegram_client.send_message) is faked here; only the orchestration
(no-op when unconfigured, per-promotion isolation, what gets passed to
send_message) is under test. Real delivery is verified live, same
convention as every other network-touching module in this codebase.
"""

from __future__ import annotations

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
