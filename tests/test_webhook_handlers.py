"""
handle_callback_query() against real LocalJsonRepository instances (a
tmp_path, not mocked) — only the outbound Telegram calls
(answer_callback_query, edit_message_text) are faked. Matches this
codebase's bias toward testing against something real rather than a mock
of the storage layer.
"""

from __future__ import annotations

from radiocomp import config
from radiocomp.models import DiscoveredVia, EntryChannel, EntryChannelType, EntryRecord, EntryStatus, Promotion
from radiocomp.notify.callback_data import build_callback_data
from radiocomp.storage.base import get_repository
from radiocomp.webhook import handlers


def _use_local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)


def _fake_telegram(monkeypatch):
    acked = []
    edited = []
    monkeypatch.setattr(
        handlers.telegram_client, "answer_callback_query", lambda cbq_id, text=None: acked.append((cbq_id, text))
    )
    monkeypatch.setattr(
        handlers.telegram_client,
        "edit_message_text",
        lambda chat_id, message_id, text, reply_markup=None: edited.append((chat_id, message_id, text, reply_markup)),
    )
    return acked, edited


def _seed_promotion_and_channel(is_free_route=True):
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)

    promo = Promotion(
        station_name_raw="Radio X",
        title="Win a Car",
        discovered_via=DiscoveredVia.DIRECT,
        source_url="https://example.com/win-a-car",
        dedup_hash="hash1",
    )
    channel = EntryChannel(
        promotion_id=promo.id,
        channel_type=EntryChannelType.WEB_FORM,
        is_free_route=is_free_route,
        review_recommended=False,
    )
    promo_repo.add(promo)
    channel_repo.add(channel)
    return promo, channel


def _callback_query(action: str, promo_id: str, channel_id: str) -> dict:
    return {
        "id": "cbq-1",
        "data": build_callback_data(action, promo_id, channel_id),
        "message": {
            "chat": {"id": 999},
            "message_id": 42,
            "text": "Win a Car\nRadio X",
        },
    }


def test_approve_creates_entry_record(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    acked, edited = _fake_telegram(monkeypatch)
    promo, channel = _seed_promotion_and_channel()

    handlers.handle_callback_query(_callback_query("a", promo.id, channel.id))

    entry_repo = get_repository("entry_records", EntryRecord)
    records = list(entry_repo.list())
    assert len(records) == 1
    assert records[0].status == EntryStatus.APPROVED
    assert records[0].promotion_id == promo.id
    assert records[0].channel_id == channel.id
    assert len(acked) == 1
    assert len(edited) == 1
    assert edited[0][3] == {"inline_keyboard": []}  # buttons explicitly cleared


def test_skip_creates_entry_record_with_skipped_status(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    _fake_telegram(monkeypatch)
    promo, channel = _seed_promotion_and_channel()

    handlers.handle_callback_query(_callback_query("s", promo.id, channel.id))

    entry_repo = get_repository("entry_records", EntryRecord)
    records = list(entry_repo.list())
    assert len(records) == 1
    assert records[0].status == EntryStatus.SKIPPED


def test_duplicate_callback_does_not_create_a_second_record(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    acked, _ = _fake_telegram(monkeypatch)
    promo, channel = _seed_promotion_and_channel()

    cbq = _callback_query("a", promo.id, channel.id)
    handlers.handle_callback_query(cbq)
    handlers.handle_callback_query(cbq)  # simulated Telegram retry

    entry_repo = get_repository("entry_records", EntryRecord)
    assert len(list(entry_repo.list())) == 1
    # Both taps still get acknowledged (spinner must always clear)
    assert len(acked) == 2


def test_malformed_callback_data_is_acknowledged_and_ignored(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    acked, edited = _fake_telegram(monkeypatch)

    handlers.handle_callback_query({"id": "cbq-1", "data": "garbage", "message": {}})

    entry_repo = get_repository("entry_records", EntryRecord)
    assert list(entry_repo.list()) == []
    assert len(acked) == 1
    assert edited == []  # no chat/message_id to edit


def test_unknown_promotion_or_channel_is_handled_gracefully(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    acked, edited = _fake_telegram(monkeypatch)

    handlers.handle_callback_query(_callback_query("a", "doesnotexist1", "doesnotexist2"))

    entry_repo = get_repository("entry_records", EntryRecord)
    assert list(entry_repo.list()) == []
    assert len(acked) == 1
