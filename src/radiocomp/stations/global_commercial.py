"""
Global Commercial (`comp.<brand>.co.uk`/`.com`) — Global's own in-house
"brand-sponsored competition" tool (internal name "Global React Studio"/
"Global Commercial"), a Next.js + Sanity CMS platform served per-brand
(`comp.smoothradio.com`, `comp.heart.co.uk`, `comp.capitalfm.com`,
`comp.classicfm.com`, `comp.lbc.co.uk`, `comp.radiox.co.uk`, ...) —
distinct from the already-built Global WIN/`winplus.*` platform
(`stations/global_win.py`), which is a different, separate system
despite both belonging to Global.

**Discovery needs no auth at all.** The entire competition — title,
dates, T&Cs URL, and the tie-breaker question/options (even the correct
answer) — is embedded directly in the page's own server-rendered HTML as
Next.js "flight data" (the `self.__next_f.push(...)` script blobs React
Server Components uses to stream props to the client), readable with a
plain `httpx` GET — confirmed live 2026-10-05/06 against the one real
competition this adapter was built against,
`https://comp.smoothradio.com/nescafe-2026/8`. No separate API, no login,
same posture as every other adapter in this codebase.

**The flight data is NOT one clean, self-contained JSON blob.** It's
React's own wire format: a sequence of `<id>:<value>` lines across
several `self.__next_f.push([1, "..."])` calls, where `<value>` is
sometimes a literal JSON object/array and sometimes a lazy `"$<id>"`
reference to another line entirely. Confirmed live that this page
happens to carry one single, fully-inlined (non-referenced) copy of the
real competition document — the same literal substring containing
`"entryMechanic":"entryMultipleChoice","entryMultipleChoice":{"answers":
[...],"correctAnswer":"Matilda","question":"..."}` and, a little further
along, `"slug":"nescafe-2026","title":"Nescafe 2026","campaign":
{"dataManagerId":2587,"client":"Nescafe","startDate":"2026-09-30
17:00:00","endDate":"2026-10-29 23:59:00","terms_url":"https://
campaign.smoothradio.com/terms-conditions/..."}`. `extract_competition_json()`
below doesn't attempt a full RSC deserialization (overkill for what's
needed, and the reference-based lines aren't needed at all) — it
concatenates every decoded push-call string into one text blob, then
locates each key of interest (`entryMechanic`, `entryMultipleChoice`,
`campaign`, `slug`, `title`, ...) by name and extracts its value with a
small string-aware brace/bracket counter, refusing (returning None for
that key) if what follows isn't an inline literal (e.g. a `"$ref"`
string) rather than guessing. This is shared by both this module and
`entry_execution/global_commercial_auth.py` (which re-parses the same
live page's own rendered DOM, via `page.content()`, to re-read the
tie-breaker's correct answer at draft/submit time) — "how do I parse
this platform's embedded JSON" exists exactly once, per the plan this
was built from.

**Conservative free/paid classification, same posture as every other
adapter.** No structured cost field was found anywhere in the Sanity
JSON — unlike Global WIN's own genuine `competitionEntryType` field —
so this never guesses "free" just because an entry form has no payment
fields. `_classify_free_paid()` looks for an explicit free-entry phrase
("free of charge", "no purchase necessary") in the real T&Cs page body
(linked via `campaign.terms_url`, a separate page from the competition
page itself). The one real competition this was built against has
*neither* phrase anywhere in its T&Cs (confirmed live) — it just
describes registering and submitting an answer, with no cost language at
all — so even this first, presumably-genuinely-free example comes back
`is_free_route=None, review_recommended=True` rather than being assumed
free. Don't loosen this just because every example seen so far probably
is free; extend the regex only once a real confirmed phrase is found on
this platform, same as every other adapter's own "no real paid/free
signal seen yet" gaps (see `stations/wayin.py`).

**Entry mechanism**: `channel_url_or_number` is the competition's own
`comp.<brand>` URL — login happens inline on this same page (a tabbed
Gigya sign-up/sign-in widget), so unlike Global WIN there's no separate
homepage/brand-resolution dance needed. See
`entry_execution/global_commercial_auth.py`'s own docstring for the
authenticated side (sign-in mechanics, and the tie-breaker auto-answer
decision — a real, deliberate, user-made call, documented prominently
there and in docs/build-log.md, not here).

**Self-registration**: `STATION_NAME`/`STATION_NETWORK` need to be a
member of `compliance/engine.py`'s `SHARED_LIMIT_NETWORKS["Global"]`,
same pattern `global_win.py`'s own `station_name_raw` already uses.

**Seed list**: no listing/index page for this platform was found during
this build (same situation as `stations/wayin.py`) — `_SEED_COMPETITION_URLS`
is deliberately just the one real, currently-live competition URL this
adapter was built and verified against, not an invented or guessed set
of others. Expand this list as more are found, same "seed manually,
expand over time" convention as `wayin.py`/`seed_local_independent.py`.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .. import config
from ..dedup import promotion_dedup_hash
from ..models import DiscoveredVia, EntryChannel, EntryChannelType, Promotion
from ..storage.base import get_repository

logger = logging.getLogger(__name__)

STATION_NAME = "Global Commercial"
STATION_NETWORK = "Global"

_SEED_COMPETITION_URLS = [
    "https://comp.smoothradio.com/nescafe-2026/8",
]

# Title-only, same conservative reasoning as global_win.py's own prize extraction — a
# body/T&Cs fallback risks picking up an unrelated figure.
_PRIZE_RE = re.compile(r"£\s?([\d,]+(?:\.\d+)?)", re.IGNORECASE)

# No real confirmed free-entry phrase has been seen yet that's specific to this
# platform — these are the same literal phrases already proven live elsewhere in this
# codebase (wayin.py's "free of charge", the common UK promo phrase "no purchase
# necessary"), reused here rather than invented fresh. The one real T&Cs fixture this
# adapter was built against matches neither — see module docstring.
_FREE_INDICATOR_RE = re.compile(r"(free of charge|no purchase necessary)", re.IGNORECASE)

_NEXT_F_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*)"\]\)\s*;?\s*$', re.DOTALL)


def _headers() -> dict:
    return {"User-Agent": config.USER_AGENT, "Accept": "text/html,application/xhtml+xml"}


def _extract_next_f_text(html: str) -> str:
    """Concatenates every `self.__next_f.push([1, "..."])` call's decoded string
    payload, in document order, into one text blob — see module docstring. Each
    `<script>` tag carrying one of these calls was confirmed live (2026-10-05/06,
    against the real nescafe-2026 fixture) to contain exactly one such call filling
    the entire tag body, so matching the whole script body against `_NEXT_F_PUSH_RE`
    (anchored to the end of the body) reliably isolates its one JS string-literal
    argument; `json.loads('"' + raw + '"')` then un-escapes it as an ordinary JSON
    string (it's valid JSON string *content*, just not wrapped in quotes in the
    source). Scripts that don't match at all (`self.__next_f.push([0])`,
    `self.__next_f.push([2,null])` — no string argument) are silently skipped, not
    treated as an error — they carry no competition data."""
    import json as _json

    texts: list[str] = []
    for script_body in re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL):
        if "self.__next_f.push" not in script_body:
            continue
        match = _NEXT_F_PUSH_RE.search(script_body)
        if not match:
            continue
        try:
            texts.append(_json.loads('"' + match.group(1) + '"'))
        except ValueError:
            continue
    return "".join(texts)


def _extract_balanced_value(text: str, key: str) -> Optional[object]:
    """Finds `"<key>":` in `text` and parses whatever JSON object/array literal
    immediately follows it, using a small string-aware brace/bracket depth counter
    (so a nested `}`/`]` inside a quoted string value, e.g. the real T&Cs-opt-in HTML
    snippet embedded in this platform's own JSON, doesn't terminate the scan early).
    Returns None if the key isn't found at all, or if what follows isn't an inline
    `{`/`[` literal (e.g. a lazy `"$<id>"` RSC reference instead — see module
    docstring) — refuses to guess rather than returning a wrong/partial value."""
    import json as _json

    marker = f'"{key}":'
    idx = text.find(marker)
    if idx == -1:
        return None

    start = idx + len(marker)
    if start >= len(text) or text[start] not in "{[":
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                try:
                    return _json.loads(text[start : i + 1])
                except ValueError:
                    return None
    return None


def _last_string_value(window: str, key: str) -> Optional[str]:
    """The last `"<key>":"<value>"` match in `window` — used to pick the real
    document's own `slug`/`title`/`metaTitle`/`metaDescription` fields out of a
    bounded window immediately before the `campaign` key, rather than the first
    occurrence of a generic key like "title" anywhere on the page (which also
    appears, unrelated, on nearly every content card — confirmed live)."""
    matches = re.findall(rf'"{key}":"((?:[^"\\]|\\.)*)"', window)
    return matches[-1] if matches else None


def extract_competition_json(html: str) -> Optional[dict]:
    """None if this doesn't look like a real Global Commercial competition page at
    all (no `entryMechanic` and no `campaign` key found anywhere in the flight data —
    a redirect, an error page, or the site's shape having changed), rather than a
    parsing gap worth guessing around. See module docstring for the full mechanics."""
    text = _extract_next_f_text(html)
    if not text:
        return None

    entry_mechanic_match = re.search(r'"entryMechanic":"([^"]*)"', text)
    entry_mechanic = entry_mechanic_match.group(1) if entry_mechanic_match else None

    entry_multiple_choice = None
    if entry_mechanic == "entryMultipleChoice":
        entry_multiple_choice = _extract_balanced_value(text, "entryMultipleChoice")

    campaign = _extract_balanced_value(text, "campaign")

    if entry_mechanic is None and campaign is None:
        return None

    campaign_idx = text.find('"campaign":')
    window = text[max(0, campaign_idx - 4000) : campaign_idx] if campaign_idx != -1 else ""

    return {
        "slug": _last_string_value(window, "slug"),
        "title": _last_string_value(window, "title"),
        "metaTitle": _last_string_value(window, "metaTitle"),
        "metaDescription": _last_string_value(window, "metaDescription"),
        "entryMechanic": entry_mechanic,
        "entryMultipleChoice": entry_multiple_choice,
        "campaign": campaign,
    }


def _tandc_text(html: str) -> str:
    """Plain server-rendered HTML (confirmed live, unlike the competition page's own
    React-hydrated content) — strip tags/scripts and normalise whitespace, same
    approach as wayin.py's own T&Cs handling of a full HTML page (as opposed to
    global_win.py's handling of an HTML-in-JSON-field)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def _classify_free_paid(tandc_text: str) -> tuple[Optional[bool], str]:
    """(is_free_route, raw_excerpt). Never returns False — no real paid competition
    has been seen yet on this platform to build a paid-signal pattern against (see
    module docstring); review_recommended is always set from whether this came back
    None, same as every other ambiguity-by-default classifier in this codebase."""
    match = _FREE_INDICATOR_RE.search(tandc_text)
    if not match:
        return None, "Global Commercial T&Cs: no explicit free/paid entry-cost language found"
    start = max(0, match.start() - 100)
    end = min(len(tandc_text), match.end() + 100)
    return True, tandc_text[start:end]


def _parse_deadline(end_date: Optional[str]) -> Optional[date]:
    """campaign.endDate is a real source field, e.g. "2026-10-29 23:59:00" — no
    timezone suffix (confirmed live); treated as-is, same posture as every other
    adapter's deadline parsing (never adjusted for an assumed timezone)."""
    if not end_date:
        return None
    try:
        return datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        return None


def parse_detail(doc: dict, source_url: str, tandc_text: str = "") -> tuple[Optional[Promotion], list[EntryChannel]]:
    """Pure. Takes the already-extracted competition dict (see
    extract_competition_json) plus the already-fetched, already-stripped T&Cs text
    (see _tandc_text) — mirrors global_win.py's own parse_detail() taking an
    already-fetched details.json body rather than doing any fetching itself.
    (None, []) if no title or no campaign block was found at all — not a real
    competition record, not a parsing gap worth guessing around."""
    # metaTitle is the real, human-facing competition title — confirmed live to be
    # exactly what the page's own <title> tag renders (e.g. "Win An Amazing Cosy
    # Set-Up Thanks To NESCAFÉ®"). The Sanity document's own "title" field, by
    # contrast, is an internal/admin label (e.g. "Nescafe 2026") — a real distinction
    # found while building this, not a guess — so metaTitle is preferred, falling back
    # to "title" only if metaTitle is ever genuinely absent.
    title = (doc.get("metaTitle") or doc.get("title") or "").strip()
    campaign = doc.get("campaign")
    # `campaign` being an empty dict ({}) still counts as "found" — only its
    # genuine absence (None, the key never appearing in the source document at
    # all) means this isn't a real competition record. `not campaign` would
    # wrongly treat a present-but-empty dict as missing (a real bug found
    # 2026-10-06, caught by a test deliberately using campaign={} to isolate
    # title-resolution behaviour from the campaign fields' own presence).
    if not title or campaign is None:
        return None, []
    campaign = campaign or {}

    deadline = _parse_deadline(campaign.get("endDate"))

    prize_match = _PRIZE_RE.search(title)
    prize_value = None
    if prize_match:
        try:
            prize_value = float(prize_match.group(1).replace(",", ""))
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

    is_free, free_excerpt = _classify_free_paid(tandc_text)
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
    """No credentials touched anywhere in this function — see module docstring. One
    real network call per seed URL for the competition page itself, plus one more for
    its linked T&Cs page (campaign.terms_url) when present."""
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    existing_hashes = {p.dedup_hash for p in promo_repo.list()}

    new_promotions: list[Promotion] = []
    new_channels: list[EntryChannel] = []
    seen_this_run: set[str] = set()

    with httpx.Client(follow_redirects=True) as client:
        for source_url in _SEED_COMPETITION_URLS:
            try:
                resp = client.get(source_url, headers=_headers(), timeout=config.REQUEST_TIMEOUT_SECONDS)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch Global Commercial competition page %s: %s", source_url, exc)
                continue

            doc = extract_competition_json(resp.text)
            if doc is None:
                logger.warning(
                    "Could not find an embedded competition document on %s — page shape may have changed",
                    source_url,
                )
                continue

            tandc_text = ""
            terms_url = (doc.get("campaign") or {}).get("terms_url")
            if terms_url:
                try:
                    terms_resp = client.get(terms_url, headers=_headers(), timeout=config.REQUEST_TIMEOUT_SECONDS)
                    terms_resp.raise_for_status()
                    tandc_text = _tandc_text(terms_resp.text)
                except httpx.HTTPError as exc:
                    logger.warning(
                        "Failed to fetch T&Cs page %s for %s — classifying conservatively as unknown: %s",
                        terms_url,
                        source_url,
                        exc,
                    )
            else:
                logger.warning(
                    "No campaign.terms_url found for %s — classifying conservatively as unknown", source_url
                )

            promo, channels = parse_detail(doc, source_url, tandc_text)
            if promo is None:
                logger.warning("Could not extract a promotion from %s — missing title/campaign", source_url)
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
        "Global Commercial ingestion: %d seed URL(s) checked, %d new promotions, %d entry channels recorded",
        len(_SEED_COMPETITION_URLS),
        len(new_promotions),
        len(new_channels),
    )
    return new_promotions, new_channels


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    promos, channels = ingest()
    for p in promos:
        print(f"[{p.entry_deadline or '?'}] {p.title}")
