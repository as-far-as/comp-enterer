"""
Loquax radio-competitions ingestion adapter.

Loquax (loquax.co.uk) is a UK comping community forum (XenForo-based) that
maintains a live, curated listing of currently-open radio competitions at
/competitions/radio-competitions.php — see the scoping research doc for
why this aggregator is worth polling rather than trying to hand-build a
scraper per radio station from day one.

What's actually on that listing page, unauthenticated: a competition
title, a "closes <date>" line (sometimes prefixed with a recurrence note
like "** Daily Entry **"), and a link through to the full forum thread.
The station name and prize detail live inside the thread itself, which
requires a Loquax forum login to read — this adapter deliberately doesn't
attempt that. It's here to catch that a competition exists and surface it
for review (via the notification layer, per the spec), not to fully
auto-resolve every field from an anonymous page load. station_name_raw
is left as "(unresolved — see Loquax thread)" pending either a logged-in
follow-up fetch (a reasonable Phase 1 addition, not built here) or the
listing simply not naming the station within the title, which happens
for a meaningful fraction of entries.

Run this file directly to do a one-off ingestion pass:
    python -m radiocomp.aggregators.loquax
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .. import config
from ..models import DiscoveredVia, Promotion
from ..storage.base import get_repository
from ..dedup import promotion_dedup_hash

logger = logging.getLogger(__name__)

LISTING_URL = "https://www.loquax.co.uk/competitions/radio-competitions.php"

# "Closes 11 September 2026" / "** Daily Entry ** Closes 4 September 2026"
_CLOSES_RE = re.compile(r"Closes\s+(\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE)


def _parse_deadline(minor_text: str) -> Optional[date]:
    match = _CLOSES_RE.search(minor_text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d %B %Y").date()
    except ValueError:
        return None


def fetch_listing_html() -> str:
    resp = httpx.get(
        LISTING_URL,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def parse_listing(html: str) -> list[Promotion]:
    soup = BeautifulSoup(html, "html.parser")
    promotions: list[Promotion] = []

    for item in soup.select(".structItem"):
        title_link = item.select_one(".structItem-title a")
        if not title_link:
            continue
        title = title_link.get_text(strip=True)
        href = title_link.get("href", "")
        source_url = href if href.startswith("http") else f"https://www.loquax.co.uk{href}"

        minor = item.select_one(".structItem-minor")
        minor_text = minor.get_text(" ", strip=True) if minor else ""
        deadline = _parse_deadline(minor_text)

        # Note: Loquax sometimes lists the same underlying thread more than
        # once (e.g. comp-235428..235431 were four listing rows for one
        # £4,000 TUI Gift Card thread, observed live during testing — almost
        # certainly one promotion cross-posted per participating station).
        # Since we can't resolve which station without a logged-in fetch of
        # the thread, these collapse to one Promotion via the dedup hash
        # below rather than being stored as indistinguishable duplicates.
        station_name_raw = "(unresolved — see Loquax thread)"

        promotions.append(
            Promotion(
                station_name_raw=station_name_raw,
                title=title,
                entry_deadline=deadline,
                discovered_via=DiscoveredVia.AGGREGATOR,
                source_url=source_url,
                dedup_hash=promotion_dedup_hash(station_name_raw, title, deadline),
            )
        )

    return promotions


def ingest() -> list[Promotion]:
    """Fetch, parse, and upsert into the promotions repository. Returns
    the list of promotions that were newly seen this run (already-known
    dedup hashes are skipped)."""

    repo = get_repository("promotions", Promotion)
    existing_hashes = {p.dedup_hash for p in repo.list()}

    html = fetch_listing_html()
    parsed = parse_listing(html)

    # Loquax sometimes lists the same underlying thread multiple times (e.g. one
    # promotion cross-posted for several stations) with nothing on the anonymous
    # listing page to tell those apart. Since station_name_raw is unresolved here
    # anyway, collapse same-hash entries within this single pass rather than
    # storing indistinguishable duplicates — see the note in parse_listing().
    seen_this_run: set[str] = set()
    deduped: list[Promotion] = []
    for p in parsed:
        if p.dedup_hash in seen_this_run:
            continue
        seen_this_run.add(p.dedup_hash)
        deduped.append(p)

    new_ones = [p for p in deduped if p.dedup_hash not in existing_hashes]
    for promo in new_ones:
        repo.add(promo)

    logger.info(
        "Loquax ingestion: %d listed (%d distinct), %d new, %d already known",
        len(parsed),
        len(deduped),
        len(new_ones),
        len(deduped) - len(new_ones),
    )
    return new_ones


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fresh = ingest()
    print(f"\n{len(fresh)} new competition(s) found:\n")
    for p in fresh:
        deadline_str = p.entry_deadline.isoformat() if p.entry_deadline else "unknown deadline"
        print(f"  - {p.title}  (closes {deadline_str})\n    {p.source_url}")
