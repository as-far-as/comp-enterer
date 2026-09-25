"""
Radio Exe direct-station monitor — second "direct monitoring" adapter,
alongside talksport.py.

Radio Exe (Exeter/Devon) runs on Nation Broadcasting's shared "Nation
Player" platform (nationplayer.com/radio-exe/...), which several other
Nation-branded local stations also use — this adapter is written against
Radio Exe specifically, but the same c-pod__* selectors (an Aiir CMS
template pattern) would likely transfer to those other stations if this
gets extended later.

Two things worth flagging, both discovered by actually fetching real pages
rather than assumed — see docs/build-log.md, 2026-09-02 for the fuller
investigation trail:

1. This looked like a strong Playwright candidate at first glance (heavy
   client-side JS, a cookie-consent interstitial, a "Website powered by
   Aiir" footer) — but both the listing and every detail page checked
   turned out to be fully server-rendered; plain httpx gets everything.
   Same lesson as talksport.py: don't assume a browser is needed just
   because a site *looks* JS-heavy — check first.

2. Entry methods here don't fit neatly into the channel types the spec
   originally anticipated. Alongside the expected web-form/SMS/phone
   channels (which read almost identically to talksport's — the same
   "charged at the standard rate" phrasing shows up here too, and gets
   the same free-route treatment for the same Gambling-Act-compliance
   reason), one live competition asked entrants to message a WhatsApp
   number or send an email — neither of which existed as an
   EntryChannelType. Added EMAIL and WHATSAPP to the model rather than
   force-fitting them into SMS or WEB_FORM, which would have been actively
   misleading (different cost profile, different — currently nonexistent —
   automation path). Both stay firmly in "capture and flag for review",
   same conservative posture as everything else here: no cost signal is
   ever visible for either in practice, so they're never confidently
   classified as free.
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

BASE_URL = "https://www.nationplayer.com"
LISTING_URL = f"{BASE_URL}/radio-exe/win/"
STATION_NAME = "Radio Exe"
STATION_NETWORK = "Nation Broadcasting"

_PRIZE_RE = re.compile(r"£\s?([\d,]+(?:\.\d+)?)\s*(?:k\b)?", re.IGNORECASE)
_DEADLINE_RE = re.compile(r"closes?\s+(?:at\s+[\d.:apm]*\s*)?on\s+(\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE)

_ONLINE_COST_RE = re.compile(r"online entry costs?\s*£\s?([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_ONLINE_ENTRY_PRESENT_RE = re.compile(r"enter\s+(?:this\s+competition\s+)?online", re.IGNORECASE)
# Presence-only signal for a web-form entry point with no cost phrase found —
# added 2026-09-08 because the cost-phrase-only check above meant a
# genuinely free web form produced NO channel at all (silent omission),
# not an ambiguous one, unlike talksport.py's equivalent case. Derived from
# the one real (paid) fixture on file ("You can enter this competition
# online using the form above." + "A single online entry costs £2.50.") —
# no real free-page fixture exists to validate this against yet. Fails
# safe either way: if the phrasing on a genuinely free page differs, the
# worst case is unchanged current behaviour (still silently drops the
# channel), never a wrongly-confident classification. See
# rendering.py's retry_ambiguous_web_form_channels for how this gets a
# second chance to resolve via a rendered-page fetch.
_SMS_KEYWORD_RE = re.compile(r"text\s+(?:the\s+word\s+)?['\"]?(\w+)['\"]?\s+to\s+(\d{4,7})", re.IGNORECASE)
_SMS_COST_RE = re.compile(r"texts?\s+(?:are|cost)\s*£\s?([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_CALL_RE = re.compile(r"call\s+(0\d[\d\s]{6,})", re.IGNORECASE)
_STANDARD_RATE_RE = re.compile(r"standard\s+(?:network\s+)?rate", re.IGNORECASE)
_WHATSAPP_RE = re.compile(r"whatsapp\D{0,20}?(\+?\d[\d\s]{6,})", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


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
    """Returns (title, detail_url) pairs from the "Win" listing page."""
    soup = BeautifulSoup(html, "html.parser")
    seen_urls: set[str] = set()
    results: list[tuple[str, str]] = []

    for link in soup.select("a.c-pod__link[href]"):
        title_el = link.select_one(".c-pod__title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = link["href"]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        results.append((title, url))

    return results


def _extract_competition_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main") or soup.body
    text = main.get_text("\n", strip=True)
    # The "On Air" schedule block follows every competition's own text
    # consistently across both fixtures checked live — cut there rather
    # than risk picking up unrelated station-schedule text as part of the
    # competition body.
    end = text.find("\nOn Air")
    return text[:end] if end != -1 else text


def _extract_channels(text: str) -> list[EntryChannel]:
    channels: list[EntryChannel] = []

    online_cost = _ONLINE_COST_RE.search(text)
    online_present = _ONLINE_ENTRY_PRESENT_RE.search(text)
    if online_cost:
        cost = float(online_cost.group(1).replace(",", ""))
        channels.append(
            EntryChannel(
                promotion_id="",
                channel_type=EntryChannelType.WEB_FORM,
                is_free_route=False,
                cost_to_entrant_gbp=cost,
                review_recommended=False,
                raw_excerpt=online_cost.group(0),
            )
        )
    elif online_present:
        # A web-form entry point exists but no cost phrase was found —
        # mirrors talksport.py's "no price mentioned at all" pattern:
        # plausibly free, not confidently classifiable from static text.
        channels.append(
            EntryChannel(
                promotion_id="",
                channel_type=EntryChannelType.WEB_FORM,
                is_free_route=None,
                review_recommended=True,
                raw_excerpt=online_present.group(0),
            )
        )

    sms_match = _SMS_KEYWORD_RE.search(text)
    if sms_match:
        cost_match = _SMS_COST_RE.search(text)
        cost = float(cost_match.group(1).replace(",", "")) if cost_match else None
        channels.append(
            EntryChannel(
                promotion_id="",
                channel_type=EntryChannelType.SMS,
                is_free_route=False if cost is not None else None,
                cost_to_entrant_gbp=cost,
                channel_url_or_number=sms_match.group(2),
                review_recommended=cost is None,
                raw_excerpt=sms_match.group(0),
            )
        )

    call_match = _CALL_RE.search(text)
    if call_match:
        # Same phrase, same Gambling Act reasoning as talksport.py's
        # PHONE_ENTRY handling: "standard rate" is a legitimate free route
        # (no more than normal contact cost) — but it's still a phone
        # channel, so still never auto-dialled regardless of this flag.
        is_free = bool(_STANDARD_RATE_RE.search(text))
        channels.append(
            EntryChannel(
                promotion_id="",
                channel_type=EntryChannelType.PHONE_ENTRY,
                is_free_route=True if is_free else None,
                cost_to_entrant_gbp=0.0 if is_free else None,
                channel_url_or_number=call_match.group(1).strip(),
                review_recommended=not is_free,
                raw_excerpt=call_match.group(0),
            )
        )

    whatsapp_match = _WHATSAPP_RE.search(text)
    if whatsapp_match:
        # No cost signal is ever visible for this route in practice —
        # WhatsApp messaging cost depends on the entrant's own data plan,
        # not something this page states. Always left for review.
        channels.append(
            EntryChannel(
                promotion_id="",
                channel_type=EntryChannelType.WHATSAPP,
                is_free_route=None,
                channel_url_or_number=whatsapp_match.group(1).strip(),
                review_recommended=True,
                raw_excerpt=whatsapp_match.group(0),
            )
        )

    email_match = _EMAIL_RE.search(text)
    if email_match:
        channels.append(
            EntryChannel(
                promotion_id="",
                channel_type=EntryChannelType.EMAIL,
                is_free_route=None,
                channel_url_or_number=email_match.group(0),
                review_recommended=True,
                raw_excerpt=email_match.group(0),
            )
        )

    return channels


def parse_detail(html: str, title: str, source_url: str) -> tuple[Promotion, list[EntryChannel]]:
    text = _extract_competition_text(html)

    # Title-only, same reasoning as talksport.py: body text mixes entry
    # costs (£2.50) in with any actual prize figure, and a wrong-but-
    # confident prize value is worse than an honest gap.
    prize_match = _PRIZE_RE.search(title)
    prize_value = None
    if prize_match:
        try:
            prize_value = float(prize_match.group(1).replace(",", ""))
            if "k" in prize_match.group(0).lower():
                prize_value *= 1000
        except ValueError:
            prize_value = None

    deadline: Optional[date] = None
    deadline_match = _DEADLINE_RE.search(text)
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

    channels = _extract_channels(text)
    return promo, channels


def ingest() -> tuple[list[Promotion], list[EntryChannel]]:
    """Fetch the listing, then every detail page it links to. Radio Exe's
    "Win" page typically only has a small handful of live competitions at
    once (unlike talkSPORT's much larger listing), so this doesn't need
    talksport.py's max_detail_pages cap — every listed competition gets
    fetched."""

    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    existing_hashes = {p.dedup_hash for p in promo_repo.list()}

    listing_html = fetch(LISTING_URL)
    listed = parse_listing(listing_html)

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
        "Radio Exe ingestion: %d listed, %d new promotions, %d entry channels recorded",
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
        deadline_str = p.entry_deadline.isoformat() if p.entry_deadline else "no fixed deadline"
        prize_str = f"£{p.prize_value_gbp:,.0f}" if p.prize_value_gbp else "prize value unclear"
        print(f"  - {p.title}  ({prize_str}, closes {deadline_str})")
        for ch in [c for c in channels if c.promotion_id == p.id]:
            flag = "REVIEW" if ch.review_recommended else ("FREE" if ch.is_free_route else "PAID")
            cost = f" £{ch.cost_to_entrant_gbp:.2f}" if ch.cost_to_entrant_gbp else ""
            print(f"      [{flag}] {ch.channel_type.value}{cost}")
