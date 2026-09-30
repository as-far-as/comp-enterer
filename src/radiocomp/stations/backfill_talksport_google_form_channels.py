"""
One-off backfill: re-check already-stored talkSPORT promotions that have
zero entry channels recorded, now that parse_detail() has a fallback for
the "prose + embedded Google Form, no 'How to Enter' heading" template
(see talksport.py's own docstring/google_forms.py, and docs/build-log.md,
2026-09-30).

A fresh discovery run won't do this on its own — ingest() skips any
promotion it already knows about (by dedup hash) entirely, never
re-fetching or re-parsing it, so promotions discovered before this fix
shipped (and so recorded with channels=[]) need this one-off pass.

Run this file directly:
    python -m radiocomp.stations.backfill_talksport_google_form_channels
"""

from __future__ import annotations

import logging

import httpx

from ..models import EntryChannel, Promotion
from ..storage.base import get_repository
from . import talksport

logger = logging.getLogger(__name__)


def backfill() -> dict[str, int]:
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)

    talksport_promos = [p for p in promo_repo.list() if p.station_name_raw == talksport.STATION_NAME]
    existing_promo_ids_with_channels = {c.promotion_id for c in channel_repo.list()}
    to_check = [p for p in talksport_promos if p.id not in existing_promo_ids_with_channels]

    checked = 0
    added = 0

    with httpx.Client() as client:
        for promo in to_check:
            checked += 1
            try:
                resp = client.get(
                    promo.source_url,
                    headers={"User-Agent": talksport.config.USER_AGENT},
                    timeout=talksport.config.REQUEST_TIMEOUT_SECONDS,
                    follow_redirects=True,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Failed to re-fetch %r (%s): %s", promo.title, promo.source_url, exc)
                continue

            _new_promo, channels = talksport.parse_detail(resp.text, promo.title, promo.source_url)
            for channel in channels:
                channel.promotion_id = promo.id
                channel_repo.add(channel)
                added += 1
                logger.info("Added %s channel for %r", channel.channel_type.value, promo.title)

    logger.info("Backfill complete: %d talkSPORT promotion(s) checked, %d channel(s) added", checked, added)
    return {"checked": checked, "added": added}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = backfill()
    print(f"\n{result['added']} channel(s) added across {result['checked']} promotion(s) checked.")
