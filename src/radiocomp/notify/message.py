"""
Builds a Telegram notification's text and inline keyboard for one
promotion. Reuses view_promotions.py's own formatting (formatting.py) so
the CLI and the Telegram message never say different things about the
same channel.

build_message_text() only ever adds the recurring-series note — the
suppression of later occurrences (deciding *whether* this promotion
should be notified at all) lives one level up, in notify/send.py, which
is the only place with repository access to check for earlier siblings.
"""

from __future__ import annotations

from typing import Optional

from ..compliance.engine import ComplianceCheck
from ..formatting import format_channel_line
from ..models import EntryChannel, Promotion
from .callback_data import build_callback_data
from .channel_selection import select_approvable_channel


def build_message_text(promotion: Promotion, channels: list[EntryChannel], compliance: ComplianceCheck) -> str:
    deadline_str = promotion.entry_deadline.isoformat() if promotion.entry_deadline else "no fixed deadline"
    prize_str = f"£{promotion.prize_value_gbp:,.0f}" if promotion.prize_value_gbp else "prize value unclear"

    lines = [
        promotion.title,
        f"{promotion.station_name_raw}  |  {prize_str}  |  closes {deadline_str}",
    ]

    if channels:
        lines.extend(format_channel_line(c).strip() for c in channels)
    else:
        lines.append("(no entry channels recorded yet)")

    if compliance.blocks_new_entry:
        lines.append(f"⚠️ {compliance.note}")

    if promotion.recurrence_series_id:
        lines.append("🔁 Recurring — this is the first occurrence found; later ones won't re-notify.")

    lines.append(promotion.source_url)
    return "\n".join(lines)


def build_reply_markup(promotion_id: str, approvable_channel: Optional[EntryChannel]) -> Optional[dict]:
    if approvable_channel is None:
        return None
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": build_callback_data("a", promotion_id, approvable_channel.id)},
                {"text": "⏭ Skip", "callback_data": build_callback_data("s", promotion_id, approvable_channel.id)},
            ]
        ]
    }


def build_notification(
    promotion: Promotion, channels: list[EntryChannel], compliance: ComplianceCheck
) -> tuple[str, Optional[dict]]:
    text = build_message_text(promotion, channels, compliance)
    approvable = select_approvable_channel(channels)
    markup = build_reply_markup(promotion.id, approvable)
    return text, markup
