"""
handle_callback_query() against real LocalJsonRepository instances (a
tmp_path, not mocked) — only the outbound Telegram calls
(answer_callback_query, edit_message_text) are faked. Matches this
codebase's bias toward testing against something real rather than a mock
of the storage layer.
"""

from __future__ import annotations

from radiocomp import config
from radiocomp.models import DiscoveredVia, EntryChannel, EntryChannelType, EntryRecord, EntryStatus, Outcome, Promotion
from radiocomp.notify.callback_data import build_callback_data
from radiocomp.storage.base import get_repository
from radiocomp.webhook import handlers


def _use_local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)


def _fake_telegram(monkeypatch):
    acked = []
    edited = []
    edited_captions = []
    monkeypatch.setattr(
        handlers.telegram_client, "answer_callback_query", lambda cbq_id, text=None: acked.append((cbq_id, text))
    )
    monkeypatch.setattr(
        handlers.telegram_client,
        "edit_message_text",
        lambda chat_id, message_id, text, reply_markup=None: edited.append((chat_id, message_id, text, reply_markup)),
    )
    monkeypatch.setattr(
        handlers.telegram_client,
        "edit_message_caption",
        lambda chat_id, message_id, caption, reply_markup=None: edited_captions.append((chat_id, message_id, caption, reply_markup)),
    )
    return acked, edited, edited_captions


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
    acked, edited, _ = _fake_telegram(monkeypatch)
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
    acked, _, _ = _fake_telegram(monkeypatch)
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
    acked, edited, _ = _fake_telegram(monkeypatch)

    handlers.handle_callback_query({"id": "cbq-1", "data": "garbage", "message": {}})

    entry_repo = get_repository("entry_records", EntryRecord)
    assert list(entry_repo.list()) == []
    assert len(acked) == 1
    assert edited == []  # no chat/message_id to edit


def test_unknown_promotion_or_channel_is_handled_gracefully(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    acked, edited, _ = _fake_telegram(monkeypatch)

    handlers.handle_callback_query(_callback_query("a", "doesnotexist1", "doesnotexist2"))

    entry_repo = get_repository("entry_records", EntryRecord)
    assert list(entry_repo.list()) == []
    assert len(acked) == 1


def _photo_callback_query(action: str, promo_id: str, channel_id: str) -> dict:
    return {
        "id": "cbq-1",
        "data": build_callback_data(action, promo_id, channel_id),
        "message": {
            "chat": {"id": 999},
            "message_id": 42,
            "caption": "📝 Draft ready: Win a Car\nRadio X",
            "photo": [{"file_id": "abc", "width": 100, "height": 100}],
        },
    }


def _seed_draft_record(promo, channel) -> EntryRecord:
    entry_repo = get_repository("entry_records", EntryRecord)
    record = EntryRecord(
        promotion_id=promo.id,
        channel_type=EntryChannelType.WEB_FORM,
        channel_id=channel.id,
        status=EntryStatus.DRAFTED,
        fill_plan={"fields": [], "notes": ""},
    )
    entry_repo.add(record)
    return record


def test_draft_submit_tap_updates_the_same_record_to_approved(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    acked, edited, edited_captions = _fake_telegram(monkeypatch)
    promo, channel = _seed_promotion_and_channel()
    draft = _seed_draft_record(promo, channel)

    handlers.handle_callback_query(_photo_callback_query("a", promo.id, channel.id))

    entry_repo = get_repository("entry_records", EntryRecord)
    records = list(entry_repo.list())
    assert len(records) == 1  # updated in place, not a second record
    assert records[0].id == draft.id
    assert records[0].status == EntryStatus.APPROVED
    assert records[0].approved_at is not None
    assert len(acked) == 1
    assert edited == []  # this was a photo message — editMessageText must not be used
    assert len(edited_captions) == 1
    assert edited_captions[0][3] == {"inline_keyboard": []}


def test_draft_reject_tap_updates_the_same_record_to_skipped(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    _fake_telegram(monkeypatch)
    promo, channel = _seed_promotion_and_channel()
    draft = _seed_draft_record(promo, channel)

    handlers.handle_callback_query(_photo_callback_query("s", promo.id, channel.id))

    entry_repo = get_repository("entry_records", EntryRecord)
    records = list(entry_repo.list())
    assert len(records) == 1
    assert records[0].id == draft.id
    assert records[0].status == EntryStatus.SKIPPED


def test_repeat_tap_on_a_resolved_draft_is_already_recorded_unchanged(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    acked, edited, edited_captions = _fake_telegram(monkeypatch)
    promo, channel = _seed_promotion_and_channel()
    _seed_draft_record(promo, channel)

    cbq = _photo_callback_query("a", promo.id, channel.id)
    handlers.handle_callback_query(cbq)
    handlers.handle_callback_query(cbq)  # simulated Telegram retry, after the record is already APPROVED

    entry_repo = get_repository("entry_records", EntryRecord)
    assert len(list(entry_repo.list())) == 1
    assert len(acked) == 2
    assert acked[1] == ("cbq-1", "Already recorded")
    assert len(edited_captions) == 2


def test_outcome_won_tap_creates_an_outcome_record(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    acked, edited, _ = _fake_telegram(monkeypatch)
    entry_repo = get_repository("entry_records", EntryRecord)
    entry = EntryRecord(
        promotion_id="p1", channel_type=EntryChannelType.WEB_FORM, channel_id="c1", status=EntryStatus.SUBMITTED
    )
    entry_repo.add(entry)

    handlers.handle_callback_query(
        {
            "id": "cbq-1",
            "data": build_callback_data("w", "p1", entry.id),
            "message": {"chat": {"id": 999}, "message_id": 7, "text": "Did you win: Win a Car?"},
        }
    )

    outcome_repo = get_repository("outcomes", Outcome)
    outcomes = list(outcome_repo.list())
    assert len(outcomes) == 1
    assert outcomes[0].entry_id == entry.id
    assert outcomes[0].won is True


def test_outcome_taps_are_deduped_like_entry_decisions(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    acked, edited, _ = _fake_telegram(monkeypatch)
    entry_repo = get_repository("entry_records", EntryRecord)
    entry = EntryRecord(
        promotion_id="p1", channel_type=EntryChannelType.WEB_FORM, channel_id="c1", status=EntryStatus.SUBMITTED
    )
    entry_repo.add(entry)

    cbq = {
        "id": "cbq-1",
        "data": build_callback_data("l", "p1", entry.id),
        "message": {"chat": {"id": 999}, "message_id": 7, "text": "Did you win: Win a Car?"},
    }
    handlers.handle_callback_query(cbq)
    handlers.handle_callback_query(cbq)

    outcome_repo = get_repository("outcomes", Outcome)
    outcomes = list(outcome_repo.list())
    assert len(outcomes) == 1
    assert outcomes[0].won is False
    assert len(acked) == 2
    assert acked[1] == ("cbq-1", "Already recorded")
