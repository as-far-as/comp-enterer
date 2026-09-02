"""
T&C snapshot capture — the data-gathering half of the compliance engine's
"first pass" (spec section 4).

Most stations put their full T&Cs on the same page discovery already
fetches (this is true for both talksport.py and radioexe.py's detail
pages), so this captures a promotion by re-fetching its own source_url
rather than needing a separate T&C-URL field or per-adapter wiring. That's
a deliberate simplification for this first pass — it costs one extra fetch
per snapshot rather than reusing the page discovery already downloaded,
but keeps this decoupled from every adapter's own parsing logic. Revisit if
that extra traffic ever matters at the volumes this actually runs at.

The two parsed fields are intentionally shallow, narrow-phrase matches
rather than an attempt to summarise arbitrary T&C prose — a live check
against talkSPORT's own fixtures found genuinely complex, multi-channel
numeric entry limits ("up to a maximum of 100 times Online", "£40 on paid
SMS entries", "116 postal entries") that no simple regex could honestly
reduce to one line, and a bare "free entry" phrase match turned out to
appear in a *paid* boost-offer clause on the same page — a real instance of
exactly the kind of confident-but-wrong extraction this project avoids
elsewhere. So both parsed fields only fire on a narrow set of known-
reliable phrasings and default to None otherwise; raw_text is what
preserves everything else for you to actually read.
"""

from __future__ import annotations

import hashlib
import re

import httpx
from bs4 import BeautifulSoup

from .. import config
from ..models import Promotion, TandCSnapshot

# Same Gambling-Act-compliant free-route vocabulary already relied on in
# talksport.py / radioexe.py's own channel classification — reusing it here
# rather than inventing a separate heuristic keeps "free route" meaning the
# same thing everywhere in this codebase.
_FREE_ROUTE_PHRASES = ["standard network rate", "standard rate", "free of charge", "no purchase necessary"]

# Only the simplest, unambiguous per-entrant limit phrasings — real T&C text
# varies far more than this catches (see module docstring), and a partial
# match here would be worse than leaving parsed_entry_limit as None.
_ENTRY_LIMIT_RE = re.compile(
    r"(?:one|1)\s+entry\s+per\s+(household|person|entrant|email address|mobile number|telephone number|day)",
    re.IGNORECASE,
)


def fetch(url: str) -> str:
    resp = httpx.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def parse_snapshot(html: str, promotion_id: str) -> TandCSnapshot:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main") or soup.body
    text = main.get_text("\n", strip=True) if main else ""
    lowered = text.lower()

    # True when a reliable phrase is found; None (never False) otherwise —
    # not finding the phrase isn't evidence a free route doesn't exist,
    # just that this shallow parser didn't recognise how it's worded here.
    free_route_exists = True if any(phrase in lowered for phrase in _FREE_ROUTE_PHRASES) else None

    limit_match = _ENTRY_LIMIT_RE.search(text)
    entry_limit = limit_match.group(0) if limit_match else None

    return TandCSnapshot(
        promotion_id=promotion_id,
        raw_text=text,
        raw_text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        parsed_entry_limit=entry_limit,
        parsed_free_route_exists=free_route_exists,
    )


def capture_snapshot(promotion: Promotion) -> TandCSnapshot:
    """Fetch promotion.source_url fresh and parse a snapshot from it."""
    html = fetch(promotion.source_url)
    return parse_snapshot(html, promotion.id)
