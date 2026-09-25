"""
One-off backfill: add the phone/post free-entry channels
bauer_makemeawinner.py should have recorded from the start (see that
module's docstring for the real gap — the user manually found and used a
free phone-line entry on a campaign this adapter had only ever recorded
as a paid web_form) to the promotions already sitting in production
before the fix shipped.

A fresh discovery run won't do this on its own — ingest() skips any
promotion it already knows about (by dedup hash) entirely, including not
re-checking its channels, so the existing 15 Bauer promotions need this
one-off pass.

Run this file directly:
    python -m radiocomp.stations.backfill_bauer_phone_post_channels
"""

from __future__ import annotations

import logging

import httpx

from ..models import EntryChannel, Promotion
from ..storage.base import get_repository
from . import bauer_makemeawinner as bmw

logger = logging.getLogger(__name__)


def backfill() -> dict[str, int]:
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)

    bauer_promos = [p for p in promo_repo.list() if p.station_name_raw == bmw.STATION_NAME]
    all_channels = list(channel_repo.list())
    existing_types_by_promo: dict[str, set] = {}
    for c in all_channels:
        existing_types_by_promo.setdefault(c.promotion_id, set()).add(c.channel_type)

    added = 0
    checked = 0

    with httpx.Client() as client:
        token = bmw.fetch_session_token(client)
        for promo in bauer_promos:
            tag = promo.source_url.rstrip("/").rsplit("/", 1)[-1]
            checked += 1
            try:
                info = bmw.fetch_campaign_info(client, token, tag)
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch T&Cs for %r (%s): %s", promo.title, tag, exc)
                continue

            text = bmw._tandc_text(info)
            already = existing_types_by_promo.get(promo.id, set())

            for extractor in (bmw.extract_phone_channel, bmw.extract_post_channel):
                channel = extractor(text)
                if channel is None or channel.channel_type in already:
                    continue
                channel.promotion_id = promo.id
                channel_repo.add(channel)
                added += 1
                logger.info("Added %s channel for %r", channel.channel_type.value, promo.title)

    logger.info("Backfill complete: %d Bauer promotion(s) checked, %d channel(s) added", checked, added)
    return {"checked": checked, "added": added}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = backfill()
    print(f"\n{result['added']} channel(s) added across {result['checked']} promotion(s).")
