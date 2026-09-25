"""
One-off backfill: re-classify already-stored talkSPORT web_form
EntryChannels that are stuck ambiguous (is_free_route=None,
review_recommended=True) against the real entry-widget pricing, via
talksport_widget.resolve_online_channel.

Exists because a fresh discovery run won't reprocess these on its own —
talksport.py dedups by (station, title, deadline) hash, so an
already-stored promotion's channels are never revisited once discovered.
The 7 real ambiguous web_form channels found in production on 2026-09-08
would otherwise sit unresolved indefinitely even after the widget fix
shipped, since they were all discovered before it existed.

Only talkSPORT has a resolver (see talksport_widget.py's docstring for
why Radio Exe's pages don't need one — they're fully server-rendered
already). Any promotion whose station_name_raw isn't "talkSPORT" is
skipped rather than guessed at.

Run this file directly:
    python -m radiocomp.stations.backfill_rendered_classification
"""

from __future__ import annotations

import logging
from collections import defaultdict

from ..models import EntryChannel, EntryChannelType, Promotion
from ..storage.base import get_repository
from . import talksport, talksport_widget

logger = logging.getLogger(__name__)


def _is_ambiguous_web_form(channel: EntryChannel) -> bool:
    return channel.channel_type == EntryChannelType.WEB_FORM and channel.is_free_route is None and channel.review_recommended


def backfill() -> dict[str, int]:
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)

    promos_by_id = {p.id: p for p in promo_repo.list()}
    channels_by_promo: dict[str, list[EntryChannel]] = defaultdict(list)
    for channel in channel_repo.list():
        channels_by_promo[channel.promotion_id].append(channel)

    updated = 0
    skipped_unknown_station = 0

    for promo_id, channels in channels_by_promo.items():
        ambiguous = [c for c in channels if _is_ambiguous_web_form(c)]
        if not ambiguous:
            continue

        promo = promos_by_id.get(promo_id)
        if promo is None:
            continue

        if promo.station_name_raw != talksport.STATION_NAME:
            skipped_unknown_station += 1
            logger.info("No known resolver for station %r (promotion %s) — skipping", promo.station_name_raw, promo.id)
            continue

        for channel in ambiguous:
            resolved = talksport_widget.resolve_online_channel(promo.source_url, channel)
            if resolved != channel:
                channel_repo.upsert(resolved)
                updated += 1
                logger.info(
                    "Resolved channel %s for %r: is_free_route None -> %s",
                    resolved.id,
                    promo.title,
                    resolved.is_free_route,
                )

    logger.info(
        "Backfill complete: %d channel(s) updated, %d promotion(s) skipped (unknown station)",
        updated,
        skipped_unknown_station,
    )
    return {"updated": updated, "skipped_unknown_station": skipped_unknown_station}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = backfill()
    print(f"\n{result['updated']} channel(s) updated, {result['skipped_unknown_station']} skipped.")
