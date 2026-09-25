"""
Decides whether a promotion has anything safe enough to show an
Approve/Skip button for. Deliberately narrow, same "don't guess" posture
as compliance/tandc.py and every adapter's channel classification: no
qualifying channel is the correct, expected default for most promotions
(aggregator-sourced ones with no channels extracted at all, or ones where
every channel is paid or flagged for review) — not a gap to work around.

WEB_FORM is deliberately excluded here, even a confidently-free one — that
channel type now goes through entry_execution/'s own draft flow (a
Playwright-filled, screenshotted draft you confirm before anything
touches the real page), never this module's immediate Approve/Skip. This
was a real gap caught while designing entry_execution/: before this
exclusion, the moment a free web_form channel was ever discovered, a tap
here would have created an EntryRecord(status=APPROVED, channel_type=
WEB_FORM) with no draft, no fill plan, no screenshot, never reviewed —
exactly what the two-stage design exists to prevent. See
docs/build-log.md, 2026-09-04, for the full reasoning.
"""

from __future__ import annotations

from typing import Optional

from ..models import EntryChannel, EntryChannelType


def select_approvable_channel(channels: list[EntryChannel]) -> Optional[EntryChannel]:
    for channel in channels:
        if channel.channel_type == EntryChannelType.WEB_FORM:
            continue
        if channel.is_free_route is True and channel.review_recommended is False:
            return channel
    return None
