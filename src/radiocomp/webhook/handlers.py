"""
The actual business logic for a Telegram callback_query update — kept
separate from app.py's routing/auth so it can be tested without spinning
up FastAPI or hitting the network (only the outbound Telegram calls it
makes need faking in tests).
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..compliance.engine import check_promotion
from ..models import EntryChannel, EntryRecord, EntryStatus, Promotion
from ..notify import telegram_client
from ..notify.callback_data import parse_callback_data
from ..storage.base import get_repository

logger = logging.getLogger(__name__)


def handle_callback_query(callback_query: dict) -> None:
    callback_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    original_text = message.get("text", "")

    parsed = parse_callback_data(data)
    if parsed is None:
        telegram_client.answer_callback_query(callback_id, "Malformed request")
        return
    action, promotion_id, channel_id = parsed

    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    entry_repo = get_repository("entry_records", EntryRecord)

    promo = promo_repo.get(promotion_id)
    channel = channel_repo.get(channel_id)
    if promo is None or channel is None:
        telegram_client.answer_callback_query(callback_id, "No longer available")
        _clear_buttons(chat_id, message_id, original_text)
        return

    existing = [
        r for r in entry_repo.list() if r.promotion_id == promotion_id and r.channel_id == channel_id
    ]
    if existing:
        telegram_client.answer_callback_query(callback_id, "Already recorded")
        _clear_buttons(chat_id, message_id, original_text, existing[0].status)
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
    _clear_buttons(chat_id, message_id, original_text, status)


def _clear_buttons(chat_id, message_id, original_text: str, status: "EntryStatus | None" = None) -> None:
    if chat_id is None or message_id is None:
        return
    suffix = {
        EntryStatus.APPROVED: "\n\n✅ Approved",
        EntryStatus.SKIPPED: "\n\n⏭ Skipped",
    }.get(status, "\n\n(no longer available)")
    try:
        # Explicit empty keyboard — editMessageText leaves the old buttons
        # live if reply_markup is omitted, it does not clear them.
        telegram_client.edit_message_text(chat_id, message_id, original_text + suffix, reply_markup={"inline_keyboard": []})
    except Exception:
        logger.exception("Failed to edit message %s in chat %s after recording decision", message_id, chat_id)
