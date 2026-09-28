"""
One-off backfill: set recurrence_series_id on the Global WIN promotions
already sitting in production from before that field existed (see
global_win.py's docstring and docs/build-log.md, 2026-09-28).

Without this, a genuinely later occurrence of an already-known recurring
series (e.g. tomorrow's "Capital's Bong Game 2026" round) would look like
the *first* sighting of that series to notify/send.py's
_is_first_of_its_series() — since the already-stored earlier rounds
still have recurrence_series_id=None, they wouldn't be recognised as
members of the same series at all, and the later round would wrongly get
notified again instead of being suppressed.

A fresh discovery run won't do this on its own — ingest() skips any
promotion it already knows about (by dedup hash) entirely, never
re-fetching or re-parsing it, so the existing Global WIN promotions need
this one-off pass.

Run this file directly:
    python -m radiocomp.stations.backfill_global_win_recurrence
"""

from __future__ import annotations

import logging

import httpx

from ..models import Promotion
from ..storage.base import get_repository
from . import global_win

logger = logging.getLogger(__name__)


def backfill() -> dict[str, int]:
    promo_repo = get_repository("promotions", Promotion)

    global_win_promos = [
        p for p in promo_repo.list() if p.station_name_raw == global_win.STATION_NAME and p.recurrence_series_id is None
    ]

    checked = 0
    updated = 0

    with httpx.Client() as client:
        for promo in global_win_promos:
            checked += 1
            comp_id = int(promo.source_url.rstrip("/").rsplit("/", 2)[-2])
            try:
                detail = global_win.fetch_competition_details(client, comp_id)
            except httpx.HTTPError as exc:
                logger.warning("Failed to re-fetch details for %r (%s): %s", promo.title, comp_id, exc)
                continue

            schedule_id = detail.get("competitionScheduleId")
            if detail.get("competitionIsRound") and schedule_id:
                promo.recurrence_series_id = str(schedule_id)
                promo_repo.upsert(promo)
                updated += 1
                logger.info("Set recurrence_series_id=%r for %r (%s)", promo.recurrence_series_id, promo.title, comp_id)

    logger.info("Backfill complete: %d Global WIN promotion(s) checked, %d updated", checked, updated)
    return {"checked": checked, "updated": updated}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = backfill()
    print(f"\n{result['updated']} promotion(s) updated across {result['checked']} checked.")
