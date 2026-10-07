"""
ThePrizeFinder Instagram-giveaways ingestion adapter.

The first source for the Instagram extension scoped in
docs/instagram-scoping-research.md. ThePrizeFinder has a dedicated
category page, /competitions/instagram-competitions, paginated via
?page=0..N (about 10 rows a page, ~100 live listings when first checked
on 2026-10-07), plain-httpx fetchable with no login. Same
`.competition-row` markup as the radio keyword search in
theprizefinder.py, with two differences: the title links straight to the
Instagram post rather than a /link-track redirect, and the closing date
is plain text ("13-10-2026 Midnight", "08-10-2026 3pm") rather than a
machine-readable <time> element.

This adapter only ever fetches theprizefinder.com — never instagram.com.
Instagram's Terms ban automated access even when logged in (scoping doc,
section 1), so everything stored here comes from the listing row alone,
and entering stays a manual step for the user.

Per the conservative-classification rule (CLAUDE.md), every channel comes
back is_free_route=None with review_recommended=True: like/follow/comment
is a free draw in law, but the listing doesn't say which mechanic a post
uses (every row just reads "Enter via Instagram"), and some giveaways are
"must buy" or require tagging friends, which the user has opted out of.
The user sees the post and decides.

Dedup is keyed on the post's shortcode (instagram.com/p/<shortcode>/)
when one can be parsed, not on promoter/title/deadline: ThePrizeFinder
links the same post in several URL shapes (/p/ID, /username/p/ID/, with
?hl= or ?img_index= query strings), and a shortcode key also lets a post
the user forwards to the bot later resolve to the same Promotion.

Not registered in run_discovery.py yet — notify.send sends one Telegram
message per new promotion, and the first pass would find ~100. It gets
registered alongside the daily digest (scoping doc, section 10).

Run this file directly to do a one-off ingestion pass:
    python -m radiocomp.aggregators.theprizefinder_instagram
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .. import config
from ..dedup import promotion_dedup_hash
from ..models import DiscoveredVia, EntryChannel, EntryChannelType, Promotion
from ..storage.base import get_repository

logger = logging.getLogger(__name__)

LISTING_URL = "https://www.theprizefinder.com/competitions/instagram-competitions"
MAX_PAGES = 20  # ~11 pages live; a hard stop in case the pager ever loops
PAGE_DELAY_SECONDS = 1.0

_SHORTCODE_RE = re.compile(r"instagram\.com/(?:[^/?#]+/)?(?:p|reel|tv)/([A-Za-z0-9_-]+)")
_DEADLINE_RE = re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b")


def instagram_shortcode(url: str) -> Optional[str]:
    match = _SHORTCODE_RE.search(url)
    return match.group(1) if match else None


def canonical_post_url(shortcode: str) -> str:
    return f"https://www.instagram.com/p/{shortcode}/"


def instagram_dedup_hash(shortcode: str) -> str:
    return promotion_dedup_hash("instagram", shortcode, None)


def _parse_deadline(text: str) -> Optional[date]:
    match = _DEADLINE_RE.search(text)
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _last_page_index(soup: BeautifulSoup) -> int:
    indices = [0]
    for link in soup.select('a[href*="page="]'):
        match = re.search(r"page=(\d+)", link.get("href", ""))
        if match:
            indices.append(int(match.group(1)))
    return min(max(indices), MAX_PAGES - 1)


def _fetch_page(client: httpx.Client, page: int) -> str:
    resp = client.get(LISTING_URL, params={"page": page})
    resp.raise_for_status()
    return resp.text


def fetch_listing_pages() -> list[str]:
    with httpx.Client(
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        first = _fetch_page(client, 0)
        pages = [first]
        for page in range(1, _last_page_index(BeautifulSoup(first, "html.parser")) + 1):
            time.sleep(PAGE_DELAY_SECONDS)
            html = _fetch_page(client, page)
            if not BeautifulSoup(html, "html.parser").select(".competition-row"):
                break
            pages.append(html)
    return pages


def parse_listing(html: str) -> list[tuple[Promotion, EntryChannel]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[Promotion, EntryChannel]] = []

    for row in soup.select(".competition-row"):
        title_link = row.select_one(".title a")
        if not title_link:
            continue
        title = title_link.get_text(strip=True)
        raw_url = title_link.get("href", "")

        # Same direct-text-node trick as theprizefinder.py, to leave out the
        # nested "(more competitions)" link. The "(IG)" suffix is kept as seen.
        promoter_div = row.select_one(".linkPrizePick")
        promoter_text = promoter_div.find(string=True, recursive=False) if promoter_div else None
        promoter = promoter_text.strip() if promoter_text else "(unknown promoter)"

        closing_el = row.select_one(".closingDate")
        deadline = _parse_deadline(closing_el.get_text(" ", strip=True)) if closing_el else None

        shortcode = instagram_shortcode(raw_url)
        if shortcode:
            post_url = canonical_post_url(shortcode)
            dedup_hash = instagram_dedup_hash(shortcode)
        else:
            # A row that doesn't link to a recognisable post (seen on ~2 of
            # 104 live rows) — kept as-is rather than dropped or guessed at.
            post_url = raw_url
            dedup_hash = promotion_dedup_hash(promoter, title, deadline)

        excerpt_parts = [
            el.get_text(" ", strip=True)
            for el in (row.select_one(".instruct"), row.select_one(".restrict"))
            if el is not None
        ]

        promotion = Promotion(
            station_name_raw=promoter,
            title=title,
            entry_deadline=deadline,
            discovered_via=DiscoveredVia.AGGREGATOR,
            source_url=post_url,
            dedup_hash=dedup_hash,
        )
        channel = EntryChannel(
            promotion_id=promotion.id,
            channel_type=EntryChannelType.INSTAGRAM,
            is_free_route=None,
            channel_url_or_number=post_url,
            review_recommended=True,
            raw_excerpt=" | ".join(excerpt_parts) or None,
        )
        results.append((promotion, channel))

    return results


def ingest() -> tuple[list[Promotion], list[EntryChannel]]:
    """Fetch every listing page, parse, and store anything not already
    known. Returns (new promotions, their entry channels)."""

    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    existing_hashes = {p.dedup_hash for p in promo_repo.list()}

    parsed: list[tuple[Promotion, EntryChannel]] = []
    for html in fetch_listing_pages():
        parsed.extend(parse_listing(html))

    new_promotions: list[Promotion] = []
    new_channels: list[EntryChannel] = []
    for promotion, channel in parsed:
        # Also guards against the same post appearing on two pages in one
        # run (rows can shift between pages while we paginate).
        if promotion.dedup_hash in existing_hashes:
            continue
        existing_hashes.add(promotion.dedup_hash)
        promo_repo.add(promotion)
        channel_repo.add(channel)
        new_promotions.append(promotion)
        new_channels.append(channel)

    logger.info(
        "ThePrizeFinder Instagram ingestion: %d listed, %d new promotions, %d entry channels recorded",
        len(parsed),
        len(new_promotions),
        len(new_channels),
    )
    return new_promotions, new_channels


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fresh, _ = ingest()
    print(f"\n{len(fresh)} new Instagram giveaway(s) found:\n")
    for p in fresh:
        deadline_str = p.entry_deadline.isoformat() if p.entry_deadline else "unknown deadline"
        print(f"  - {p.title}  ({p.station_name_raw}, closes {deadline_str})\n    {p.source_url}")
