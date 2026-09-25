"""
The actual business logic for a Telegram callback_query update — kept
separate from app.py's routing/auth so it can be tested without spinning
up FastAPI or hitting the network (only the outbound Telegram calls it
makes need faking in tests).

Three distinct flows share the same "a"/"s"/"w"/"l" callback_data encoding
(see notify/callback_data.py):
  - a fresh discovery Approve/Skip decision (no existing EntryRecord) —
    the original flow, unchanged.
  - a draft Submit/Reject decision — an existing DRAFTED + WEB_FORM
    EntryRecord for that (promotion_id, channel_id) is updated in place
    (APPROVED/SKIPPED) rather than creating a second record. This is the
    entry-execution engine's own two-stage confirmation
    (entry_execution/notify_draft.py sends the same "a"/"s" encoding with
    different button text, precisely so the same handler recognises it).
  - an outcome Won/No response ("w"/"l") — id2 is an entry_id, not a
    channel_id; dispatched before any promotion/channel lookup since
    outcome callbacks don't carry one.

A draft confirmation is sent as a photo (send_photo), so its message has
no "text", only a "caption" — every helper here threads an is_photo flag
through so the right Telegram edit method (editMessageText vs
editMessageCaption) gets called.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..compliance.engine import check_promotion
from ..models import EntryChannel, EntryChannelType, EntryRecord, EntryStatus, Outcome, Promotion
from ..notify import telegram_client
from ..notify.callback_data import parse_callback_data
from ..storage.base import get_repository

logger = logging.getLogger(__name__)

_ALREADY_RECORDED_SUFFIX = {
    EntryStatus.APPROVED: "\n\n✅ Approved",
    EntryStatus.SKIPPED: "\n\n⏭ Skipped",
    EntryStatus.SUBMITTED: "\n\n✅ Submitted",
    EntryStatus.FAILED: "\n\n❌ Failed",
}


def handle_callback_query(callback_query: dict) -> None:
    callback_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    is_photo = "photo" in message
    original_text = message.get("caption", "") if is_photo else message.get("text", "")

    parsed = parse_callback_data(data)
    if parsed is None:
        telegram_client.answer_callback_query(callback_id, "Malformed request")
        return
    action, id1, id2 = parsed

    if action in ("w", "l"):
        _handle_outcome_response(callback_id, chat_id, message_id, original_text, is_photo, action, id1, id2)
    else:
        _handle_entry_decision(callback_id, chat_id, message_id, original_text, is_photo, action, id1, id2)


def _handle_entry_decision(
    callback_id: str, chat_id, message_id, original_text: str, is_photo: bool, action: str, promotion_id: str, channel_id: str
) -> None:
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    entry_repo = get_repository("entry_records", EntryRecord)

    promo = promo_repo.get(promotion_id)
    channel = channel_repo.get(channel_id)
    if promo is None or channel is None:
        telegram_client.answer_callback_query(callback_id, "No longer available")
        _clear_buttons(chat_id, message_id, original_text, "\n\n(no longer available)", is_photo)
        return

    existing = [
        r for r in entry_repo.list() if r.promotion_id == promotion_id and r.channel_id == channel_id
    ]

    draft = next(
        (r for r in existing if r.status == EntryStatus.DRAFTED and r.channel_type == EntryChannelType.WEB_FORM),
        None,
    )
    if draft is not None:
        _handle_draft_decision(callback_id, chat_id, message_id, original_text, is_photo, action, draft)
        return

    if existing:
        telegram_client.answer_callback_query(callback_id, "Already recorded")
        suffix = _ALREADY_RECORDED_SUFFIX.get(existing[0].status, "\n\n(no longer available)")
        _clear_buttons(chat_id, message_id, original_text, suffix, is_photo)
        return

    # Re-checked fresh here, not reused from whatever was true when the
    # notification was sent — hours can pass before a tap, and another
    # approval in the meantime could change the answer.
    check = check_promotion(promo, list(promo_repo.list()), list(entry_repo.list()))

    status = EntryStatus.APPROVED if action == "a" else EntryStatus.SKIPPED
    record = EntryRecord(
        promotion_id=promotion_id,
        channel_type=channel.channel_type,
        channel_id=channel_id,
        status=status,
        approved_at=datetime.utcnow() if status == EntryStatus.APPROVED else None,
        compliance_note=check.note,
    )
    entry_repo.add(record)
    logger.info("Recorded %s for promotion %s channel %s", status.value, promotion_id, channel_id)

    telegram_client.answer_callback_query(callback_id, "Approved ✅" if status == EntryStatus.APPROVED else "Skipped ⏭")
    suffix = "\n\n✅ Approved" if status == EntryStatus.APPROVED else "\n\n⏭ Skipped"
    _clear_buttons(chat_id, message_id, original_text, suffix, is_photo)


def _handle_draft_decision(
    callback_id: str, chat_id, message_id, original_text: str, is_photo: bool, action: str, draft: EntryRecord
) -> None:
    """action="a" is the draft's "✅ Submit" button (queues it for the next
    submit_one() pass, via APPROVED — this tap itself never touches the
    real page, no second LLM call, replaying the saved fill_plan later is
    what entry_execution/submit.py does); "s" is "❌ Reject" (SKIPPED,
    permanent, exactly like a regular Skip)."""
    entry_repo = get_repository("entry_records", EntryRecord)

    if action == "a":
        draft.status = EntryStatus.APPROVED
        draft.approved_at = datetime.utcnow()
        ack_text = "Approved — will submit shortly ✅"
        suffix = "\n\n✅ Approved — submitting shortly"
    else:
        draft.status = EntryStatus.SKIPPED
        ack_text = "Rejected ❌"
        suffix = "\n\n❌ Rejected"

    entry_repo.upsert(draft)
    logger.info("Draft %s -> %s", draft.id, draft.status.value)

    telegram_client.answer_callback_query(callback_id, ack_text)
    _clear_buttons(chat_id, message_id, original_text, suffix, is_photo)


def _handle_outcome_response(
    callback_id: str, chat_id, message_id, original_text: str, is_photo: bool, action: str, promotion_id: str, entry_id: str
) -> None:
    entry_repo = get_repository("entry_records", EntryRecord)
    outcome_repo = get_repository("outcomes", Outcome)

    entry = entry_repo.get(entry_id)
    if entry is None:
        telegram_client.answer_callback_query(callback_id, "No longer available")
        _clear_buttons(chat_id, message_id, original_text, "\n\n(no longer available)", is_photo)
        return

    existing = [o for o in outcome_repo.list() if o.entry_id == entry_id]
    if existing:
        telegram_client.answer_callback_query(callback_id, "Already recorded")
        suffix = "\n\n🏆 Won!" if existing[0].won else "\n\n❌ Didn't win"
        _clear_buttons(chat_id, message_id, original_text, suffix, is_photo)
        return

    won = action == "w"
    outcome_repo.add(Outcome(entry_id=entry_id, won=won))
    logger.info("Recorded outcome won=%s for entry %s", won, entry_id)

    telegram_client.answer_callback_query(callback_id, "Recorded 🏆" if won else "Recorded")
    suffix = "\n\n🏆 Won!" if won else "\n\n❌ Didn't win"
    _clear_buttons(chat_id, message_id, original_text, suffix, is_photo)


def _clear_buttons(chat_id, message_id, original_text: str, suffix: str, is_photo: bool = False) -> None:
    if chat_id is None or message_id is None:
        return
    try:
        # Explicit empty keyboard — editMessageText/editMessageCaption leave
        # the old buttons live if reply_markup is omitted, they don't clear
        # them on their own.
        if is_photo:
            telegram_client.edit_message_caption(chat_id, message_id, original_text + suffix, reply_markup={"inline_keyboard": []})
        else:
            telegram_client.edit_message_text(chat_id, message_id, original_text + suffix, reply_markup={"inline_keyboard": []})
    except Exception:
        logger.exception("Failed to edit message %s in chat %s after recording decision", message_id, chat_id)
