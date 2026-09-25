"""
Telegram messages for the entry-execution engine's own flow — distinct
from notify/message.py, which is specifically for the discovery
notification. Reuses the same callback_data encoding as that module
(build_callback_data("a"/"s", promotion_id, channel_id)) — only the button
label text differs ("Submit"/"Reject" instead of "Approve"/"Skip"), so
webhook/handlers.py's branching is driven entirely by whether an existing
DRAFTED WEB_FORM EntryRecord exists for that key, not by a different
action letter.
"""

from __future__ import annotations

from ..models import EntryChannel, EntryRecord, Promotion
from ..notify import telegram_client
from ..notify.callback_data import build_callback_data
from .. import config
from . import screenshots
from .fill_plan import FormMapping


def build_draft_reply_markup(promotion_id: str, channel_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Submit", "callback_data": build_callback_data("a", promotion_id, channel_id)},
                {"text": "❌ Reject", "callback_data": build_callback_data("s", promotion_id, channel_id)},
            ]
        ]
    }


def send_draft_confirmation(promo: Promotion, channel: EntryChannel, record: EntryRecord, screenshot_local_path: str) -> None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    caption = (
        f"📝 Draft ready: {promo.title}\n"
        f"{promo.station_name_raw}\n\n"
        f"Filled and ready to submit — review the screenshot, then tap Submit or Reject."
    )
    with open(screenshot_local_path, "rb") as f:
        photo_bytes = f.read()
    telegram_client.send_photo(
        config.TELEGRAM_CHAT_ID,
        photo_bytes,
        caption=caption,
        reply_markup=build_draft_reply_markup(promo.id, channel.id),
    )


def send_manual_input_flag(promo: Promotion, channel: EntryChannel, mapping: FormMapping) -> None:
    """The "worth your five minutes" case (spec section 6) — a creative/
    skill-based or unmappable field means the whole draft is refused, no
    buttons, just a plain heads-up pointing at the source page."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    text = (
        f"✍️ Needs your own input: {promo.title}\n"
        f"{promo.station_name_raw}\n\n"
        f"This form has a field that shouldn't be auto-filled (a creative/"
        f"skill-based question, or something I couldn't confidently map) — "
        f"worth your five minutes rather than a generated answer.\n\n"
        f"{promo.source_url}"
    )
    telegram_client.send_message(config.TELEGRAM_CHAT_ID, text)


def send_submission_result(promo: Promotion, record: EntryRecord) -> None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    if record.status.value == "submitted":
        caption = f"✅ Submitted: {promo.title}\n{promo.station_name_raw}"
        if record.submitted_screenshot_path:
            photo_bytes = screenshots.load_screenshot_bytes(record.submitted_screenshot_path)
            telegram_client.send_photo(config.TELEGRAM_CHAT_ID, photo_bytes, caption=caption)
        else:
            telegram_client.send_message(config.TELEGRAM_CHAT_ID, caption)
    else:
        text = f"❌ Submission failed: {promo.title}\n{promo.station_name_raw}\n\n{record.submission_error or 'Unknown error'}"
        telegram_client.send_message(config.TELEGRAM_CHAT_ID, text)
