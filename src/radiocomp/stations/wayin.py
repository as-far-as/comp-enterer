"""
xd.wayin.com ("Grow by Zeta") — a third-party competition-hosting platform
found live behind outbound links on *other* stations' own pages, not
something with any enumerable index of its own. There's no listing API or
campaign directory to poll (unlike bauer_makemeawinner.py's
api.winhappy.com), so campaigns are discovered by scanning a small,
manually-maintained seed list of pages already known to link out to one —
same "seed manually, expand over time" convention as
seed_local_independent.py/seed_southeast_london.py, just applied to
linking pages rather than stations themselves.

Two real linking pages were captured to build this adapter (2026-09-11),
re-confirmed live rather than typed in from the plan's original memory of
them (per CLAUDE.md's "never guess a URL" rule, and because both original
examples had, predictably, moved on):

1. KMFM's own /win/ page (https://www.kmfm.co.uk/win/) — a plain
   server-rendered page with a literal
   `<a href="https://xd.wayin.com/display/container/dc/.../details">` link
   to a Gousto-sponsored "Ultimate Kitchen Upgrade" campaign.
2. The plan's original Bauer "STARTUPBUNDLE" example has since expired —
   its current successor on Hits Radio's own site
   (hellorayo.co.uk/hits-radio/competitions/win/...) now embeds via a
   *different* provider (display.engagesciences.com, not wayin.com) — so
   the real, currently-live Bauer/Rayo example used instead is a shared
   Tesco Clubcard competition
   (hellorayo.co.uk/hits-radio/competitions/win/tesco-clubcard-september-26-sponsored).
   Rayo's site is a client-rendered Next.js app, and the wayin.com URL
   never appears as a real `<a href>` there at all — it only exists as a
   string value buried inside the page's embedded __NEXT_DATA__ JSON (an
   "embeds" field with `"provider": "wayin"`), rendered into a widget
   client-side. find_wayin_links() therefore looks two ways: a normal
   BeautifulSoup `<a href>` scan (catches KMFM's shape, and is what the
   original plan assumed would be enough on its own) AND a plain regex
   scan of the raw page text/JSON for any wayin.com URL substring (catches
   Rayo's shape) — confirmed necessary empirically: the `<a>`-only scan
   finds nothing at all on the Rayo linking page.

Both wayin.com campaign pages themselves turned out to be plain,
server-rendered HTML — a plain httpx GET returns the full real content
(title, prize copy, entry period, and — when present — T&Cs), no
Playwright needed, confirmed empirically for both (2026-09-11).

KMFM is actually owned by KM Media Group, not Bauer — but the campaign
page's own T&Cs (captured in the KMFM fixture) describe it as a shared
Bauer-network competition in its own words ("Anyone who has won a Bauer
competition ... on any Bauer Radio Brand, will not be eligible ..."), and
list "KMFM Group" alongside dozens of Bauer/Hits Radio Network station
brands sharing the exact same prize pool. So `network="Bauer"` is used
for the KMFM seed entry too — confirmed from the real campaign's own
T&Cs, not assumed from KMFM's own on-air branding — so
compliance/engine.py's existing `SHARED_LIMIT_NETWORKS["Bauer"]`
cross-brand entry-limit check applies correctly to it.

Free/paid signal: only one of the two real campaigns says anything
explicit about entry cost at all. KMFM's Gousto campaign states, in its
own T&Cs body text, "Online entry is free of charge." verbatim — a
confident, real signal, so that one's WEB_FORM channel comes back
`is_free_route=True`. The Tesco Clubcard campaign's page has no
T&Cs/rules content in its static HTML at all (its "Rules" tab apparently
isn't populated the same way for every campaign on this platform) and no
cost/charge language anywhere in what *is* there — so, same conservative
"never guess" posture as every other adapter in this codebase, it comes
back `is_free_route=None, review_recommended=True` rather than inferring
"free" just because the entry form itself has no payment fields. No real
*paid* wayin.com campaign has been seen yet to build a paid-signal
pattern against — if one ever turns up with its own clear cost language,
extend `_extract_free_signal` then, the same way bauer_makemeawinner.py's
phone/post extraction was extended after a real gap was found.

Prize value: neither real campaign states a single £ prize figure (one's
a travel-and-dining package, the other a kitchen-goods bundle) — always
`None` for now, same "prefer None over a wrong guess" rule as every other
adapter; nothing here manufactures a number from a field that isn't
actually present.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .. import config
from ..dedup import promotion_dedup_hash
from ..models import DiscoveredVia, EntryChannel, EntryChannelType, Promotion
from ..storage.base import get_repository

logger = logging.getLogger(__name__)

_WAYIN_HOST_HINT = "wayin.com"
# Matches any bare wayin.com URL appearing anywhere in a page's raw
# text/HTML/JSON — not just inside a real <a href> — see module docstring
# for why the Rayo/Bauer linking page needs this rather than a tag scan
# alone. Excludes the usual HTML/JSON delimiter characters so it doesn't
# swallow a trailing quote/tag from surrounding markup.
_WAYIN_URL_RE = re.compile(r"https?://[^\s\"'<>\\]*wayin\.com[^\s\"'<>\\]*", re.IGNORECASE)

# Confirmed live on both real campaign pages (2026-09-11), just with
# different real phrasing either side of it: KMFM's "Open from Friday
# 21st August 2026 ... to Friday 11th September 2026" and the Tesco
# Clubcard page's "Competition is open from Tuesday 1st Septemer at 00:01
# and closes on Wednesday 30th September 2026" (sic — the site's own
# typo, left as-is since this only scopes the search window, it doesn't
# get compared against anything). Whichever full day+month+year date
# appears *last* inside that window is the closing/end date — the
# opening date is sometimes given without a year (Tesco) and sometimes
# with one (KMFM), so "last full date, whichever form" is what actually
# holds across both real examples, not "the second date" or "the date
# near a specific keyword".
_ENTRY_PERIOD_RE = re.compile(r"open\s+from\b(.{0,300}?)(?:\.|$)", re.IGNORECASE | re.DOTALL)
_FULL_DATE_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)\s+([A-Za-z]+)\s+(\d{4})")

# The only real confirmed phrasing seen so far (KMFM/Gousto's T&Cs) — see
# module docstring. Deliberately literal rather than a broader "free"
# guess, same posture as every regex-based classifier in this codebase.
_FREE_ONLINE_RE = re.compile(r"online\s+entry\s+is\s+free\s+of\s+charge", re.IGNORECASE)

_SEED_LINK_SOURCES = [
    {
        # Hits Radio's own competitions/win page — one of many Bauer/Rayo
        # station sites that can surface a live wayin.com campaign; the
        # campaign itself is a shared, network-wide prize (see module
        # docstring), so it's attributed to "Bauer" rather than to Hits
        # Radio specifically, same convention as bauer_makemeawinner.py's
        # own STATION_NAME/STATION_NETWORK split.
        "page_url": "https://www.hellorayo.co.uk/hits-radio/competitions/win/tesco-clubcard-september-26-sponsored",
        "station_name_raw": "Bauer",
        "network": "Bauer",
    },
    {
        "page_url": "https://www.kmfm.co.uk/win/",
        "station_name_raw": "KMFM",
        "network": "Bauer",  # confirmed live from the campaign's own T&Cs — see module docstring
    },
]


def find_wayin_links(page_url: str) -> list[str]:
    """Empty list on a fetch failure (logged, not raised) — same "a quiet
    page isn't an error" posture as watch_for_competitions.py's own
    check_for_competition_link(). Matches on href/URL *host*, not link
    text — a wayin.com campaign link is never phrased as "Win..." on the
    linking page itself, it's just whatever CTA button text/graphic that
    page happens to use."""
    try:
        resp = httpx.get(
            page_url,
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch linking page %s: %s", page_url, exc)
        return []

    html = resp.text
    found: list[str] = []
    seen: set[str] = set()

    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = urljoin(page_url, link["href"])
        if _WAYIN_HOST_HINT in href.lower() and href not in seen:
            seen.add(href)
            found.append(href)

    # See module docstring — the Rayo/Bauer linking page needs this raw
    # scan too, since its wayin.com URL is never a real <a href>.
    for match in _WAYIN_URL_RE.finditer(html):
        url = match.group(0)
        if url not in seen:
            seen.add(url)
            found.append(url)

    return found


def fetch_campaign(url: str) -> str:
    resp = httpx.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def _extract_deadline(page_text: str) -> Optional[date]:
    match = _ENTRY_PERIOD_RE.search(page_text)
    if not match:
        return None
    dates = _FULL_DATE_RE.findall(match.group(1))
    if not dates:
        return None
    day, month, year = dates[-1]  # last full date in the window = the closing date, see regex comment above
    try:
        return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
    except ValueError:
        return None


def _extract_free_signal(page_text: str) -> tuple[Optional[bool], str]:
    """(is_free_route, raw_excerpt). Never returns False — no real paid
    wayin.com campaign has been seen yet to build that pattern against
    (see module docstring); the caller always sets review_recommended
    from whether this came back None, exactly like every other
    ambiguity-by-default classifier in this codebase."""
    match = _FREE_ONLINE_RE.search(page_text)
    if not match:
        return None, "wayin.com campaign page: no explicit free/paid entry-cost language found"
    start = max(0, match.start() - 100)
    end = min(len(page_text), match.end() + 100)
    return True, page_text[start:end]


def parse_detail(
    html: str, source_url: str, station_name_raw: str, network: str
) -> tuple[Optional[Promotion], list[EntryChannel]]:
    """Pure. (None, []) if no <title> can be found at all — every real
    wayin.com campaign page has one (confirmed on both real fixtures), so
    its absence means this isn't a real campaign detail page (a redirect
    wrapper, an error page, a since-removed campaign) rather than a
    parsing gap worth guessing around."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    if not title:
        return None, []

    page_text = soup.get_text(" ", strip=True)
    deadline = _extract_deadline(page_text)
    is_free, free_excerpt = _extract_free_signal(page_text)

    promo = Promotion(
        station_name_raw=station_name_raw,
        network=network,
        title=title,
        prize_value_gbp=None,  # never observed on this platform yet — see module docstring
        entry_deadline=deadline,
        discovered_via=DiscoveredVia.DIRECT,
        source_url=source_url,
        dedup_hash=promotion_dedup_hash(station_name_raw, title, deadline),
    )

    channel = EntryChannel(
        promotion_id="",
        channel_type=EntryChannelType.WEB_FORM,
        is_free_route=is_free,
        cost_to_entrant_gbp=0.0 if is_free else None,
        channel_url_or_number=source_url,
        review_recommended=is_free is None,
        raw_excerpt=free_excerpt,
    )
    return promo, [channel]


def ingest() -> tuple[list[Promotion], list[EntryChannel]]:
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    existing_hashes = {p.dedup_hash for p in promo_repo.list()}

    new_promotions: list[Promotion] = []
    new_channels: list[EntryChannel] = []
    seen_this_run: set[str] = set()
    total_links_found = 0

    for source in _SEED_LINK_SOURCES:
        page_url = source["page_url"]
        station_name_raw = source["station_name_raw"]
        network = source["network"]

        links = find_wayin_links(page_url)
        total_links_found += len(links)

        for link in links:
            try:
                html = fetch_campaign(link)
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch wayin.com campaign %s (via %s): %s", link, page_url, exc)
                continue

            promo, channels = parse_detail(html, link, station_name_raw, network)
            if promo is None:
                logger.warning(
                    "Could not extract a promotion from wayin.com campaign %s (via %s) — no <title> found",
                    link,
                    page_url,
                )
                continue

            if promo.dedup_hash in seen_this_run or promo.dedup_hash in existing_hashes:
                continue
            seen_this_run.add(promo.dedup_hash)

            promo_repo.add(promo)
            new_promotions.append(promo)
            for channel in channels:
                channel.promotion_id = promo.id
                channel_repo.add(channel)
                new_channels.append(channel)

    logger.info(
        "wayin.com ingestion: %d listed, %d new promotions, %d entry channels recorded",
        total_links_found,
        len(new_promotions),
        len(new_channels),
    )
    return new_promotions, new_channels


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    promos, channels = ingest()
    for p in promos:
        print(f"[{p.entry_deadline or '?'}] {p.title}")
