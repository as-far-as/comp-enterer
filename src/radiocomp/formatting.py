"""
Shared display formatting for an EntryChannel — the FREE/PAID/REVIEW line
used by view_promotions.py's CLI output and notify/message.py's Telegram
text, kept in one place so the two don't drift apart.
"""

from __future__ import annotations

from .models import EntryChannel


def format_channel_line(channel: EntryChannel) -> str:
    if channel.review_recommended:
        flag = "REVIEW"
    elif channel.is_free_route:
        flag = "FREE"
    elif channel.is_free_route is False:
        flag = "PAID"
    else:
        flag = "REVIEW"
    cost = f" £{channel.cost_to_entrant_gbp:.2f}" if channel.cost_to_entrant_gbp else ""
    return f"      [{flag}] {channel.channel_type.value}{cost}"
