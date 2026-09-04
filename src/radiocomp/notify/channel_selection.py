"""
Decides whether a promotion has anything safe enough to show an
Approve/Skip button for. Deliberately narrow, same "don't guess" posture
as compliance/tandc.py and every adapter's channel classification: no
qualifying channel is the correct, expected default for most promotions
(aggregator-sourced ones with no channels extracted at all, or ones where
every channel is paid or flagged for review) — not a gap to work around.
"""

from __future__ import annotations

from typing import Optional

from ..models import EntryChannel


def select_approvable_channel(channels: list[EntryChannel]) -> Optional[EntryChannel]:
    for channel in channels:
        if channel.is_free_route is True and channel.review_recommended is False:
            return channel
    return None
