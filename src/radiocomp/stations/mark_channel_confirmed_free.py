"""
One-off maintenance tool: mark a specific, already-stored EntryChannel as
confirmed free, after the user has personally checked the real page
themselves and confirmed it genuinely costs nothing to enter.

This is the clean way to unblock a channel this project's own classifiers
left ambiguous (is_free_route=None, review_recommended=True) rather than
writing a one-off "bypass eligibility" code path — the eligibility/draft/
submit pipeline (entry_execution/) is unchanged and already trusted; this
tool just corrects the one input it reads (EntryChannel.is_free_route/
review_recommended), the same way a human-in-the-loop correction to an
automated classifier should look. The very next entry-execution run picks
it up through the normal, already-tested path — no separate draft
mechanism, no shortcut around the human-approval gate before a real
submission.

Run this file directly, passing one or more real channel ids:
    python -m radiocomp.stations.mark_channel_confirmed_free <channel_id> [<channel_id> ...]
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from ..models import EntryChannel
from ..storage.base import get_repository

logger = logging.getLogger(__name__)


def mark_confirmed_free(channel_id: str) -> EntryChannel:
    channel_repo = get_repository("entry_channels", EntryChannel)
    channel = channel_repo.get(channel_id)
    if channel is None:
        raise ValueError(f"no EntryChannel with id {channel_id!r}")

    channel.is_free_route = True
    channel.cost_to_entrant_gbp = 0.0
    channel.review_recommended = False
    channel.raw_excerpt = f"Manually confirmed free by the user after checking the real page ({date.today().isoformat()})."
    channel_repo.upsert(channel)
    logger.info("Marked channel %s (promotion %s) as confirmed free", channel.id, channel.promotion_id)
    return channel


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python -m radiocomp.stations.mark_channel_confirmed_free <channel_id> [<channel_id> ...]")
        sys.exit(1)
    for cid in sys.argv[1:]:
        mark_confirmed_free(cid)
