"""
talkSPORT direct-station monitor — the first "direct monitoring" adapter
from the spec's discovery engine (as distinct from the aggregator-ingestion
adapters like loquax.py).

Two things worth flagging up front, both discovered by actually fetching
real pages rather than assumed:

1. Plain httpx reaches talkSPORT's site fine — no Playwright/headless
   Chromium needed here. The earlier finding that talkSPORT was
   unreachable was specific to the research session's fetch-tool proxy,
   not a general block; this container's own outbound network gets a
   normal 200. Worth remembering per-adapter rather than assuming every
   station needs full browser automation — reserve Playwright for sites
   that actually turn out to need JS rendering or block plain HTTP
   clients, and check before building rather than assuming.

2. talkSPORT's real competition pages are messier than the spec's
   discovery-engine section implied. Each competition typically lists
   several entry channels (SMS, Online, Post, sometimes "Free phone
   entry") with genuinely varied free/paid status, and the label on a
   channel is not reliable evidence of its actual cost: "Free phone
   entry" was observed live to mean "billed at your standard network
   rate" (a legitimate Gambling Act free-route — no more than normal
   contact cost — but not literally zero-cost), while "Online" sometimes
   means a free web form and sometimes means a paid entry-bundle
   purchase, distinguishable only by reading the clause text. Given the
   compliance engine's core invariant is "never let an entry touch a
   paid channel," this adapter is deliberately conservative: it only
   marks a channel is_free_route=True when the actual clause text gives
   unambiguous evidence, and otherwise leaves is_free_route=None with
   review_recommended=True rather than guessing. A human glance at the
   raw_excerpt it stores is cheap; a wrongly-automated paid entry is not.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .. import config
from ..models import DiscoveredVia, EntryChannel, EntryChannelType, Promotion
from ..storage.base import get_repository
from ..dedup import promotion_dedup_hash

logger = logging.getLogger(__name__)

LISTING_URL = "https://talksport.com/competitions/"
STATION_NAME = "talkSPORT"
STATION_NETWORK = "talkSPORT / News UK"

_DEADLINE_RE = re.compile(
    r"closes\s+at\s+[\d.:apm]*\s*(\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE
)
_PRIZE_RE = re.compile(r"£\s?([\d,]+(?:\.\d+)?)\s*(?:k\b)?", re.IGNORECASE)
_MONEY_RE = re.compile(r"£\s?([\d,]+(?:\.\d+)?)")

# Known "How to Enter" subsection headings, in the order they're checked —
# longer/more-specific headings first so "Online Carrier Billing" matches
# before the generic "Online" would.
_CHANNEL_HEADINGS: list[tuple[str, EntryChannelType]] = [
    ("Online Carrier Billing", EntryChannelType.WEB_FORM),
    ("Text message/SMS", EntryChannelType.SMS),
    ("Free phone entry", EntryChannelType.PHONE_ENTRY),
    ("Post", EntryChannelType.POST),
    ("App", EntryChannelType.APP),
    ("Online", EntryChannelType.WEB_FORM),
]


def fetch(url: str) -> str:
    resp = httpx.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def parse_listing(html: str) -> list[tuple[str, str]]:
    """Returns (title, detail_url) pairs from the competitions listing page."""
    soup = BeautifulSoup(html, "html.parser")
    seen_urls: set[str] = set()
    results: list[tuple[str, str]] = []

    for a in soup.select('a[href*="/competitions/"]'):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        # Real competition detail links look like /competitions/<id>/<slug>/ —
        # this filters out the "Competitions" nav link and the "page/2/" pager.
        if not title or not re.match(r"^/competitions/\d+/", href):
            continue
        url = href if href.startswith("http") else f"https://talksport.com{href}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        results.append((title, url))

    return results


def _extract_how_to_enter_block(page_text: str) -> str:
    start = page_text.find("How to Enter")
    if start == -1:
        return ""
    # Cut off at the next major T&C heading — "Entry limits" is the one
    # observed consistently across all three fixtures; fall back to a
    # generous fixed window if it's not found so we still get something.
    end = page_text.find("Entry limits", start)
    if end == -1:
        end = start + 3000
    return page_text[start:end]


def _split_into_channel_sections(how_to_enter_text: str) -> list[tuple[EntryChannelType, str]]:
    # Find every heading's position, then slice the text between consecutive
    # matches. Headings are matched as whole lines (get_text('\n') puts each
    # logical block on its own line in these pages).
    lines = how_to_enter_text.split("\n")
    heading_positions: list[tuple[int, EntryChannelType]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        for heading_text, channel_type in _CHANNEL_HEADINGS:
            if stripped == heading_text:
                heading_positions.append((i, channel_type))
                break

    sections: list[tuple[EntryChannelType, str]] = []
    for idx, (line_no, channel_type) in enumerate(heading_positions):
        next_line_no = heading_positions[idx + 1][0] if idx + 1 < len(heading_positions) else len(lines)
        body = "\n".join(lines[line_no + 1 : next_line_no]).strip()
        sections.append((channel_type, body))
    return sections


def _classify_channel(channel_type: EntryChannelType, body: str) -> EntryChannel:
    excerpt = body[:400]

    if channel_type == EntryChannelType.POST:
        is_free = "free of charge" in body.lower()
        return EntryChannel(
            promotion_id="",  # filled in by caller
            channel_type=channel_type,
            is_free_route=is_free if is_free else None,
            cost_to_entrant_gbp=0.0 if is_free else None,
            review_recommended=not is_free,
            raw_excerpt=excerpt,
        )

    if channel_type == EntryChannelType.PHONE_ENTRY:
        lowered = body.lower()
        if "standard network rate" in lowered or "standard rate" in lowered:
            # A legitimate Gambling Act free route (no more than normal contact
            # cost) — but still a phone channel, so still never auto-dialled.
            return EntryChannel(
                promotion_id="",
                channel_type=channel_type,
                is_free_route=True,
                cost_to_entrant_gbp=0.0,
                review_recommended=False,
                raw_excerpt=excerpt,
            )
        return EntryChannel(
            promotion_id="",
            channel_type=channel_type,
            is_free_route=None,
            review_recommended=True,
            raw_excerpt=excerpt,
        )

    # SMS / WEB_FORM / APP: look for a "charged at £X" / bundle-pricing signal.
    money_matches = _MONEY_RE.findall(body)
    charged_signal = "charged" in body.lower() or "entries cost" in body.lower()
    if money_matches and charged_signal:
        try:
            cheapest = min(float(m.replace(",", "")) for m in money_matches)
        except ValueError:
            cheapest = None
        return EntryChannel(
            promotion_id="",
            channel_type=channel_type,
            is_free_route=False,
            cost_to_entrant_gbp=cheapest,
            review_recommended=False,
            raw_excerpt=excerpt,
        )
    if not money_matches and body:
        # No price mentioned at all — plausibly a free web form, but this is
        # exactly the low-confidence case the module docstring warns about.
        return EntryChannel(
            promotion_id="",
            channel_type=channel_type,
            is_free_route=None,
            review_recommended=True,
            raw_excerpt=excerpt,
        )
    return EntryChannel(
        promotion_id="",
        channel_type=channel_type,
        is_free_route=None,
        review_recommended=True,
        raw_excerpt=excerpt,
    )


def parse_detail(html: str, title: str, source_url: str) -> tuple[Optional[Promotion], list[EntryChannel]]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main") or soup.body
    text = main.get_text("\n", strip=True)

    if "now closed" in text.lower()[:2000]:
        return None, []

    # Deliberately title-only: the intro paragraph on non-cash-prize pages
    # (a trip, an experience) often mentions the *entry cost* ("Entries cost
    # £2.50") before any prize figure, or has no £ figure for the prize at
    # all — a body-text fallback was tried and, live, actually picked up
    # £2.50 (the SMS cost) as the "prize value" for a trip competition with
    # no £ headline. The title is reliably the prize figure when there is
    # one (these are marketing headlines — "Chance to win £X..."), so a
    # missing match here means leaving prize_value_gbp as None rather than
    # guessing from body text, per the module's stated bias against
    # confident-looking wrong data over an honest gap.
    prize_match = _PRIZE_RE.search(title)
    prize_value = None
    if prize_match:
        try:
            prize_value = float(prize_match.group(1).replace(",", ""))
            if "k" in prize_match.group(0).lower():
                prize_value *= 1000
        except ValueError:
            prize_value = None

    deadline_match = _DEADLINE_RE.search(text)
    deadline: Optional[date] = None
    if deadline_match:
        try:
            deadline = datetime.strptime(deadline_match.group(1), "%d %B %Y").date()
        except ValueError:
            deadline = None

    promo = Promotion(
        station_name_raw=STATION_NAME,
        network=STATION_NETWORK,
        title=title,
        prize_value_gbp=prize_value,
        entry_deadline=deadline,
        discovered_via=DiscoveredVia.DIRECT,
        source_url=source_url,
        dedup_hash=promotion_dedup_hash(STATION_NAME, title, deadline),
    )

    how_to_enter = _extract_how_to_enter_block(text)
    sections = _split_into_channel_sections(how_to_enter)
    channels = [_classify_channel(ctype, body) for ctype, body in sections]

    return promo, channels


def ingest(max_detail_pages: int = 10) -> tuple[list[Promotion], list[EntryChannel]]:
    """Fetch the listing, then fetch up to `max_detail_pages` detail pages
    (newest first) and parse each. Capped by default to be a polite,
    predictable amount of traffic per run — see the technical spec's
    Cloud Run cost section for why bounding a single run's work matters
    once this is scheduled hourly rather than run by hand."""

    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    existing_hashes = {p.dedup_hash for p in promo_repo.list()}

    listing_html = fetch(LISTING_URL)
    listed = parse_listing(listing_html)[:max_detail_pages]

    new_promotions: list[Promotion] = []
    new_channels: list[EntryChannel] = []
    seen_this_run: set[str] = set()

    for title, url in listed:
        try:
            detail_html = fetch(url)
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            continue

        promo, channels = parse_detail(detail_html, title, url)
        if promo is None:
            logger.info("Skipping closed competition: %s", title)
            continue
        if promo.dedup_hash in seen_this_run or promo.dedup_hash in existing_hashes:
            continue
        seen_this_run.add(promo.dedup_hash)

        promo_repo.add(promo)
        new_promotions.append(promo)

        for ch in channels:
            ch.promotion_id = promo.id
            channel_repo.add(ch)
            new_channels.append(ch)

    logger.info(
        "talkSPORT ingestion: %d listed, %d new promotions, %d entry channels recorded",
        len(listed),
        len(new_promotions),
        len(new_channels),
    )
    return new_promotions, new_channels


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    promos, channels = ingest()
    print(f"\n{len(promos)} new competition(s):\n")
    for p in promos:
        deadline_str = p.entry_deadline.isoformat() if p.entry_deadline else "unknown deadline"
        prize_str = f"£{p.prize_value_gbp:,.0f}" if p.prize_value_gbp else "prize value unclear"
        print(f"  - {p.title}  ({prize_str}, closes {deadline_str})")
        for ch in [c for c in channels if c.promotion_id == p.id]:
            flag = "REVIEW" if ch.review_recommended else ("FREE" if ch.is_free_route else "PAID")
            cost = f" £{ch.cost_to_entrant_gbp:.2f}" if ch.cost_to_entrant_gbp else ""
            print(f"      [{flag}] {ch.channel_type.value}{cost}")
