"""
Bauer Media's shared "Make Me A Winner" competition platform
(makemeawinner.co.uk) — syndicated across Absolute Radio, Kiss, Magic,
Hits Radio, Greatest Hits Radio, and Planet Rock. Not tied to any single
station, unlike talksport.py/radioexe.py — modelled with
station_name_raw="Make Me A Winner (Bauer)", network="Bauer", so the
compliance engine's cross-brand shared-limit logic
(SHARED_LIMIT_NETWORKS["Bauer"]) applies correctly.

Two things worth flagging, both discovered by actually testing rather
than assumed:

1. makemeawinner.co.uk's own HTML is a pure client-rendered Vue SPA — a
   plain fetch gets nothing but an empty `<div id="app">`. But the app's
   real data comes from a clean, unauthenticated-by-design JSON API
   (`api.winhappy.com`, confirmed live via Playwright network-request
   capture, then confirmed working through plain httpx alone — no
   Playwright needed for this adapter at all): GET /session/data returns
   a short-lived guest bearer token in its `X-Session` response header
   (no login, no cookies — a fresh guest session every call), then that
   token authorizes GET /campaign/page/HOME, which returns every current
   competition with a genuine `is_free` boolean field straight from
   Bauer's own backend — no text-classification/regex guessing needed at
   all for this source, a first for this codebase. Real data at the time
   this was built: 0 of the ~15 live campaigns were free (matches the
   "everything's paid" pattern already seen elsewhere) — this adapter
   exists so a free one gets caught confidently and immediately the
   moment one appears, not because one currently does.
2. A companion investigation into heart.co.uk (Global) found its own
   entry widget requires a real login to Global's Gigya SSO account
   system to behave correctly — merely loading a competition page without
   being logged in showed a misleading "successfully entered" message
   (confirmed, via network-request monitoring, that no real submission
   request was ever sent — a front-end bug in their widget, not a real
   entry). Storing a real personal Global login is a materially bigger,
   new category of credential this project hasn't taken on, so Heart was
   dropped rather than built against a platform that misleads when read
   passively. No such issue was found here — Bauer's listing page loads
   safely with an empty, unmodified basket every time.

`BUNDLE`-type items (e.g. "Win Over £1 Million Bundle") are paid
entry-multiplier add-ons for campaigns already listed separately, not
distinct competitions — skipped, not modelled as their own Promotion.

A real gap found and fixed after this adapter first shipped (2026-09-09):
a paid `WEB_FORM` campaign (`is_free: false`) routinely has a genuinely
free PHONE and/or POST alternative described only in its own T&Cs body
text — the Gambling Act's required "no purchase necessary" equal-cost
route — which the summary listing endpoint never mentions at all. The
user found this manually (entered for free via the phone line on a
campaign this adapter had only recorded as paid) before this adapter
extracted it. Confirmed live, per campaign, via a second API call
(`GET /campaign/info/{tag}`, its `body` field is the full T&Cs HTML) —
not every campaign has both routes (some have neither), so each is only
recorded when its own real signal is actually found in that campaign's
own T&Cs text, same "never guess, extract per-campaign" posture as
`is_free` itself. **Tracked for visibility only, per CLAUDE.md — a phone
channel is never auto-dialled, full stop, regardless of how it's
classified.**
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Optional

import httpx

from .. import config
from ..dedup import promotion_dedup_hash
from ..models import DiscoveredVia, EntryChannel, EntryChannelType, Promotion
from ..storage.base import get_repository

logger = logging.getLogger(__name__)

_API_BASE = "https://api.winhappy.com"
_SITE_BASE = "https://makemeawinner.co.uk"
STATION_NAME = "Make Me A Winner (Bauer)"
STATION_NETWORK = "Bauer"

_PRIZE_RE = re.compile(r"£\s?([\d,]+(?:\.\d+)?)\s*(?:k\b)?", re.IGNORECASE)
# Title-only, same conservative reasoning as talksport.py's own prize
# extraction — a body/summary fallback risks picking up an unrelated
# figure (e.g. a bundle's per-entry price) rather than the actual prize.

# Confirmed live across multiple real campaigns' T&Cs bodies (2026-09-09):
# "PHONE Entrants can enter ... by calling 0372 376 7519. ... Calls (from
# the UK) are charged at standard network rate." — same Gambling-Act
# "standard rate = legitimate free route, but still a phone channel, never
# auto-dialled" reasoning as talksport.py's/radioexe.py's own PHONE_ENTRY
# handling. Bounded to the text right after the "PHONE Entrants" heading
# (not an open-ended search) so it can't accidentally match a phone number
# quoted somewhere else in a long T&Cs document for an unrelated purpose.
# 800 chars, not a tighter guess — real campaigns list several alternate
# numbers before the "standard network rate" sentence appears (confirmed
# live: a 400-char window cut off mid-list, before that sentence, and
# wrongly left the channel unclassified).
_PHONE_HEADING_RE = re.compile(r"PHONE Entrants can enter(.{0,800})", re.IGNORECASE | re.DOTALL)
_CALL_NUMBER_RE = re.compile(r"calling\s+(0\d[\d\s]{6,}\d)", re.IGNORECASE)
_STANDARD_RATE_RE = re.compile(r"standard\s+(?:network\s+)?rate", re.IGNORECASE)

# Confirmed live across multiple real campaigns, in two different real
# phrasings: "POST Entrants can also enter by sending their name..." and
# "POST Postal entries must be received... Entrants can enter the
# Competition by sending..." — matched on the bare "POST Entrants"/"POST
# Postal" heading rather than the fuller sentence, since the sentence
# itself varies but the heading word pairing has been consistent so far.
# Post is definitionally free-of-charge (beyond the entrant's own
# postage) — same convention as talksport.py's POST handling.
_POST_HEADING_RE = re.compile(r"\bPOST\s+(?:Entrants|Postal)\b(.{0,800})", re.IGNORECASE | re.DOTALL)
# The real address spans two comma-separated segments after "PO Box <n>"
# ("PO Box 8162, Derby, DE1 9GU") — a lazy match that stops at the first
# comma (confirmed live) misses the postcode entirely; match everything
# up to the postcode pattern instead, however many commas sit in between.
_PO_BOX_RE = re.compile(r"(PO Box\s+[\w\- ,]+?[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})", re.IGNORECASE)


def _headers(bearer: Optional[str] = None) -> dict:
    headers = {
        "User-Agent": config.USER_AGENT,
        "Referer": f"{_SITE_BASE}/",
        "Accept": "application/json, text/plain, */*",
    }
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers


def fetch_session_token(client: httpx.Client) -> str:
    resp = client.get(f"{_API_BASE}/session/data", headers=_headers(), timeout=config.REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    token = resp.headers.get("x-session")
    if not token:
        raise RuntimeError("winhappy session/data response had no X-Session header")
    return token


def fetch_listing(client: httpx.Client, bearer: str) -> dict:
    resp = client.get(
        f"{_API_BASE}/campaign/page/HOME", headers=_headers(bearer), timeout=config.REQUEST_TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    return resp.json()


def fetch_campaign_info(client: httpx.Client, bearer: str, tag: str) -> dict:
    resp = client.get(
        f"{_API_BASE}/campaign/info/{tag}", headers=_headers(bearer), timeout=config.REQUEST_TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    return resp.json()


def _tandc_text(info: dict) -> str:
    """The campaign/info body is real HTML (paragraphs, bold, entities) —
    strip tags and normalise the handful of entities actually observed
    live (&pound;/&nbsp;) rather than pulling in a full HTML-entity
    decoder for two characters."""
    body = info.get("body") or ""
    text = re.sub(r"<[^<]+?>", " ", body)
    text = text.replace("&pound;", "£").replace("&nbsp;", " ").replace("&rsquo;", "'").replace("&ldquo;", '"').replace(
        "&rdquo;", '"'
    )
    return re.sub(r"\s+", " ", text)


def _epoch_ms_to_date(value: Optional[int]) -> Optional[date]:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date()


def extract_phone_channel(tandc_text: str) -> Optional[EntryChannel]:
    """None if this campaign has no phone entry route at all — not every
    campaign does (confirmed live), and that's a real absence, not a
    parsing failure worth flagging for review."""
    heading_match = _PHONE_HEADING_RE.search(tandc_text)
    if not heading_match:
        return None
    section = heading_match.group(0)

    number_match = _CALL_NUMBER_RE.search(section)
    is_standard_rate = bool(_STANDARD_RATE_RE.search(section))
    return EntryChannel(
        promotion_id="",
        channel_type=EntryChannelType.PHONE_ENTRY,
        is_free_route=True if is_standard_rate else None,
        cost_to_entrant_gbp=0.0 if is_standard_rate else None,
        channel_url_or_number=number_match.group(1).strip() if number_match else None,
        review_recommended=not is_standard_rate,
        raw_excerpt=section[:400],
    )


def extract_post_channel(tandc_text: str) -> Optional[EntryChannel]:
    """None if this campaign has no postal entry route at all."""
    heading_match = _POST_HEADING_RE.search(tandc_text)
    if not heading_match:
        return None
    section = heading_match.group(0)

    address_match = _PO_BOX_RE.search(section)
    return EntryChannel(
        promotion_id="",
        channel_type=EntryChannelType.POST,
        is_free_route=True,
        cost_to_entrant_gbp=0.0,
        channel_url_or_number=address_match.group(1).strip() if address_match else None,
        review_recommended=False,
        raw_excerpt=section[:400],
    )


def parse_campaign_item(item: dict, tandc_text: Optional[str] = None) -> tuple[Promotion, list[EntryChannel]]:
    """item: one entry from campaign/page/HOME's groups[].items[], already
    filtered by the caller to type == "CAMPAIGN" (BUNDLE items are paid
    add-ons, not distinct competitions — see module docstring).

    tandc_text: this campaign's own T&Cs body (via fetch_campaign_info +
    _tandc_text), if fetched — optional and separate from the listing
    fetch, since it's a second real API call. Pure function either way:
    the caller does all the I/O, this only ever classifies text/data
    already in hand — same split as every other adapter's parse_detail()."""
    title = item["title"].strip()
    tag = item["tag"]
    deadline = _epoch_ms_to_date(item.get("end_date"))
    source_url = f"{_SITE_BASE}/campaign/{tag}"

    prize_match = _PRIZE_RE.search(title)
    prize_value = None
    if prize_match:
        try:
            prize_value = float(prize_match.group(1).replace(",", ""))
            if "k" in prize_match.group(0).lower():
                prize_value *= 1000
        except ValueError:
            prize_value = None

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

    # is_free comes straight from Bauer's own backend — a genuine boolean,
    # not a text-classification guess, so this is the one channel in this
    # codebase that can be confidently classified without a
    # review_recommended fallback either way.
    is_free = item.get("is_free")
    web_form_channel = EntryChannel(
        promotion_id="",
        channel_type=EntryChannelType.WEB_FORM,
        is_free_route=bool(is_free) if is_free is not None else None,
        cost_to_entrant_gbp=0.0 if is_free else None,
        channel_url_or_number=source_url,
        review_recommended=is_free is None,
        raw_excerpt=f"api.winhappy.com campaign/page/HOME: is_free={is_free!r}",
    )
    channels = [web_form_channel]

    # A paid web_form campaign routinely has its own separate, genuinely
    # free PHONE/POST "no purchase necessary" alternative described only
    # in the T&Cs — never assume paid-online means no free route exists
    # at all (a real gap this adapter shipped with initially — see module
    # docstring). Tracked for visibility only; never automated.
    if tandc_text:
        phone_channel = extract_phone_channel(tandc_text)
        if phone_channel:
            channels.append(phone_channel)
        post_channel = extract_post_channel(tandc_text)
        if post_channel:
            channels.append(post_channel)

    return promo, channels


def ingest() -> tuple[list[Promotion], list[EntryChannel]]:
    """Unlike talksport.py/radioexe.py, the listing call alone
    (campaign/page/HOME) already has everything needed for the web_form
    channel (title, dates, is_free). A second per-campaign call
    (campaign/info/{tag}) is still needed for the phone/post channels,
    since those only ever appear in each campaign's own T&Cs body, never
    in the listing summary."""
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    existing_hashes = {p.dedup_hash for p in promo_repo.list()}

    new_promotions: list[Promotion] = []
    new_channels: list[EntryChannel] = []

    with httpx.Client() as client:
        try:
            token = fetch_session_token(client)
            data = fetch_listing(client, token)
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch Make Me A Winner listing: %s", exc)
            return new_promotions, new_channels

        items = [item for group in data.get("groups", []) for item in group.get("items", [])]
        campaign_items = [item for item in items if item.get("type") == "CAMPAIGN"]

        seen_this_run: set[str] = set()
        for item in campaign_items:
            tandc_text = None
            try:
                info = fetch_campaign_info(client, token, item["tag"])
                tandc_text = _tandc_text(info)
            except httpx.HTTPError as exc:
                logger.warning(
                    "Failed to fetch T&Cs for %r: %s — recording the web_form channel only, "
                    "no phone/post detection this run",
                    item.get("tag"),
                    exc,
                )

            try:
                promo, channels = parse_campaign_item(item, tandc_text)
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping malformed campaign item %r: %s", item.get("tag"), exc)
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
        "Make Me A Winner ingestion: %d listed, %d new promotions, %d entry channels recorded",
        len(campaign_items),
        len(new_promotions),
        len(new_channels),
    )
    return new_promotions, new_channels


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    promos, channels = ingest()
    for p in promos:
        print(f"[{p.entry_deadline or '?'}] {p.title}")
