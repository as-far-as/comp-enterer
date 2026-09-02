"""
ThePrizeFinder radio-competitions ingestion adapter.

ThePrizeFinder (theprizefinder.com) is a UK competitions-listing site
(Drupal-based). Unlike Loquax, it has no dedicated "radio competitions"
category — its taxonomy is organised by prize theme (TV, social media,
creative, etc.), not by broadcast medium, confirmed by checking its sitemap
and site nav (see docs/build-log.md, 2026-09-02). The closest available
discovery mechanism is its keyword search, which matches promoter/company
names as well as titles: /search/competitions?keys=radio surfaces mostly
genuine radio-station promoters (Virgin Radio, Smooth Radio, Radio X, ...)
but also picks up at least one non-station false positive that just happens
to contain the word ("Radio Times", the listings magazine — observed live
during testing).

This adapter deliberately does *not* try to filter that out here. Per the
project's conservative-extraction posture (see CLAUDE.md), guessing which
"Radio ___" promoters are real stations is exactly the kind of confident-
but-possibly-wrong classification to avoid — station_name_raw is captured
as seen, same as loquax.py, and matching against real Station records (or
rejecting non-matches) is left to a future normalizer step, not invented
here.

Each result row *does* give us a promoter name and a machine-readable
closing datetime directly (unlike Loquax, which only exposes those inside
a login-gated thread) — see parse_listing().

Run this file directly to do a one-off ingestion pass:
    python -m radiocomp.aggregators.theprizefinder
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .. import config
from ..models import DiscoveredVia, Promotion
from ..storage.base import get_repository
from ..dedup import promotion_dedup_hash

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.theprizefinder.com/search/competitions?keys=radio"


def _parse_deadline(time_el) -> Optional[date]:
    if time_el is None:
        return None
    raw = time_el.get("datetime")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def fetch_listing_html() -> str:
    resp = httpx.get(
        SEARCH_URL,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def parse_listing(html: str) -> list[Promotion]:
    soup = BeautifulSoup(html, "html.parser")
    promotions: list[Promotion] = []

    for row in soup.select(".competition-row"):
        title_link = row.select_one(".title a")
        if not title_link:
            continue
        title = title_link.get_text(strip=True)
        source_url = title_link.get("href", "")

        # The promoter div's own text sits before its nested "(more
        # competitions)" link — pull just that direct text node rather than
        # get_text() on the whole div, which would pick up the link text too.
        promoter_div = row.select_one(".linkPrizePick")
        promoter_text = promoter_div.find(string=True, recursive=False) if promoter_div else None
        station_name_raw = promoter_text.strip() if promoter_text else "(unknown promoter)"

        deadline = _parse_deadline(row.select_one(".closingDate time"))

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

    new_ones = [p for p in parsed if p.dedup_hash not in existing_hashes]
    for promo in new_ones:
        repo.add(promo)

    logger.info(
        "ThePrizeFinder ingestion: %d listed, %d new, %d already known",
        len(parsed),
        len(new_ones),
        len(parsed) - len(new_ones),
    )
    return new_ones


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fresh = ingest()
    print(f"\n{len(fresh)} new competition(s) found:\n")
    for p in fresh:
        deadline_str = p.entry_deadline.isoformat() if p.entry_deadline else "unknown deadline"
        print(f"  - {p.title}  ({p.station_name_raw}, closes {deadline_str})\n    {p.source_url}")
