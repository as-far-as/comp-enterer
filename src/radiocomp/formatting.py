"""
Shared display formatting for an EntryChannel — the FREE/PAID/REVIEW line
used by view_promotions.py's CLI output and notify/message.py's Telegram
text, kept in one place so the two don't drift apart.
"""

from __future__ import annotations

from .models import EntryChannel, EntryChannelType

# Channel types whose channel_url_or_number is genuinely actionable contact
# info (a number to call/text, an address to write to, an inbox to email) —
# worth surfacing directly, since these are never automated (PHONE_ENTRY,
# ON_AIR_CALL_IN — see CLAUDE.md) or aren't automatable at all (POST), so
# a human has to act on this manually every time. Added 2026-09-10 after a
# real gap: this info was being *stored* (channel_url_or_number) but never
# actually *shown*, so a genuinely free phone/postal route sat invisible in
# every notification — the user found one only by clicking through and
# reading the source page themselves. WEB_FORM is deliberately excluded —
# its channel_url_or_number is just the promotion's own source_url, already
# shown separately, and EntryChannelType.SMS/EMAIL/WHATSAPP are included
# since their contact info is just as manually-actionable.
_SHOW_CONTACT_INFO_FOR = frozenset(
    {
        EntryChannelType.PHONE_ENTRY,
        EntryChannelType.ON_AIR_CALL_IN,
        EntryChannelType.POST,
        EntryChannelType.SMS,
        EntryChannelType.EMAIL,
        EntryChannelType.WHATSAPP,
    }
)


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
    contact = ""
    if channel.channel_type in _SHOW_CONTACT_INFO_FOR and channel.channel_url_or_number:
        contact = f" — {channel.channel_url_or_number}"
    return f"      [{flag}] {channel.channel_type.value}{cost}{contact}"
