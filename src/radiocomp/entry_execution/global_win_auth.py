"""
Global WIN (winplus.*) entry-execution companion — a station-specific
sibling to `stations/talksport_widget.py`, scoped to entry-execution
rather than discovery. See `stations/global_win.py`'s own docstring for
the platform background: `ingest()` there needs no credentials at all
(free/paid status is a public JSON field), but *entering* a competition
turns out to need a real signed-in session — a live investigation (this
session, 2026-09-28) found zero `<form>`/`<input>` elements exist
anywhere in the DOM on a real competition page until *after* "Step 1:
Sign in with your global iD" completes. There is no anonymous entry form
at all; signing in is the entry mechanism itself, not a UI nicety.

Two more things the same investigation found, both load-bearing for the
design here:

1. A direct `page.goto()` straight to a competition's own deep-link URL
   (`https://winplus.<brand>/competition/<id>/<slug>`) — exactly what
   `entry_execution/browser.py`'s generic `open_page()` does — reliably
   crashes Global's own frontend JS on a cold load (a real bug in their
   SPA's `competition-view-*.js` component, not ours:
   `TypeError: Cannot read properties of null (reading 'prize')`).
   Loading the competition's own brand homepage first, then clicking
   through in-app (organic SPA navigation, no deep link), loads the exact
   same page with zero JS errors — confirmed live 2026-09-28 against
   `https://www.winplus.co.uk/` (a real, currently-live competition,
   id 13399, "Win a £250 supermarket voucher") and
   `https://winplus.radiox.co.uk/` (id 13771, "Win Two Tickets to See
   Manic Street Preachers and Suede", tagged `brands: [67, 6]` — Global
   Player + Radio X only, no Heart at all). So `open_authenticated_page()`
   below never falls back to a bare `goto()` for the target URL — that's
   the specific path confirmed to crash.
2. Which brand homepage actually shows a given competition depends on its
   own `brands` array (same field `stations/global_win.py`'s docstring
   already documents) — confirmed live 2026-09-28 that
   `https://www.winplus.co.uk/` (the platform's own generic "winplus"
   brand, id 9) does *not* list competition 13771 at all (it's tagged
   `[67, 6]`, not `9`), so the homepage must be resolved per-competition,
   not hardcoded to one brand.

Sign-in itself is driven against Global Player's own real sign-in page
(`https://www.globalplayer.com/signin/`), not any winplus subdomain —
confirmed live (2026-09-28, passively: page loaded, consent dismissed,
fields inspected, nothing typed or submitted) to have a real Sourcepoint
consent modal (same `iframe[id^="sp_message_iframe"]` + "Accept" markup
already proven on win.talksport.com — see `entry_execution/browser.py`'s
`dismiss_consent_banner()`) and a real login form: `<input id="email"
name="email" type="email">`, `<input id="password" name="password"
type="password">`, a `rememberMe` checkbox, and a `button[type="submit"]`
labelled "Sign In" — no other submit-type button on the page. Driving
this real form (rather than reusing `stations/global_win.py`'s existing
`login()`, a REST-only Gigya call that returns a bearer token for
Global's own BFF API but never touches the Playwright browser's own
cookie jar) lets Global's own JS set whatever real session state
(`gigya.accounts.session.verify()`, cookies, etc.) each winplus subdomain's
own frontend actually checks for, rather than us needing to reverse-
engineer and replicate that cross-domain SSO handshake ourselves.
`login()` itself is untouched and unused by this module — a separate,
idle capability, as before.

**The real first login is deliberately not something this module, or any
agent, does unsupervised.** `config.GLOBAL_PLAYER_EMAIL`/
`GLOBAL_PLAYER_PASSWORD` are real Secret Manager secrets that exist but
are not bound anywhere this codebase can reach yet (see docs/build-log.md)
— `sign_in()` raises `RuntimeError` immediately if either is unset, before
any navigation is attempted, same inline-truthiness idiom
`stations/global_win.py`'s own `login()` already uses. Every mechanic in
this module short of that real login (the sign-in *page* loading, the
consent dismiss, the field selectors, the homepage-resolution logic, the
click-through-by-id anchor match) was verified live against the real
site; the actual first submission with real credentials is the user's
own action, later, once this is deployed — see docs/build-log.md.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from typing import Optional

import httpx

from .. import config
from .browser import dismiss_consent_banner

logger = logging.getLogger(__name__)

_SIGNIN_URL = "https://www.globalplayer.com/signin/"

# Same shared backend every winplus.* brand instance reads from, regardless
# of which brand homepage a competition is actually reached through — see
# stations/global_win.py's own docstring ("every brand instance is the
# same shared backend"). Deliberately not imported from stations/global_win.py
# (which keeps its own private copies of these same URLs) — this module
# stays self-contained rather than reaching into another module's private
# constants, per this task's scope (stations/global_win.py isn't touched
# beyond what it already is).
_SITE_BASE = "https://winplus.heart.co.uk"
_INIT_URL = f"{_SITE_BASE}/data/init.json"
_LIST_URL = f"{_SITE_BASE}/data/competitions/list.json"

_COMPETITION_ID_RE = re.compile(r"/competition/(\d+)/")

# Real winplus.* homepage per Global brand code — read verbatim off the
# real T&Cs text already captured in
# tests/fixtures/global_win_competition_details_13771_non_heart_brand.json
# ("...visit the 'Win Two tickets...' Promotion page on one of Global's
# participating Global Win platforms (www.winplus.heart.co.uk,
# www.winplus.capitalfm.com, www.winplus.smoothradio.com,
# www.winplus.radiox.co.uk, www.winplus.goldradiouk.com,
# www.winplus.classicfm.com, www.winplus.lbc.co.uk,
# www.winplus.capitalxtra.com, www.winplus.co.uk, www.winplus.bigtop40.com,
# www.winplus.globalplayer.com)..."), keyed by the real brand codes
# confirmed live in /data/init.json (2026-09-28) — every domain below was
# separately confirmed live to resolve with a 200 (plain httpx, following
# redirects). Note goldradio's winplus domain (goldradiouk.com) is *not*
# the same domain as its own main site (goldradio.com, per init.json's own
# `brands.goldradio.meta.link`) — a real quirk, not a typo.
#
# `rivieraradio` (id 100, `brandRegion: "world"`) is deliberately absent:
# it's not in the real T&Cs platform list above, and no real competition
# observed so far is tagged with it as its only brand. If one ever is,
# `_resolve_homepage_for_competition` fails closed (raises) rather than
# guessing a homepage for it.
_BRAND_CODE_TO_HOMEPAGE = {
    "heart": "https://www.winplus.heart.co.uk/",
    "capitalfm": "https://www.winplus.capitalfm.com/",
    "smoothradio": "https://www.winplus.smoothradio.com/",
    "radiox": "https://www.winplus.radiox.co.uk/",
    "goldradio": "https://www.winplus.goldradiouk.com/",
    "classicfm": "https://www.winplus.classicfm.com/",
    "lbc": "https://www.winplus.lbc.co.uk/",
    "capitalxtra": "https://www.winplus.capitalxtra.com/",
    "winplus": "https://www.winplus.co.uk/",
    "bigtop40": "https://www.winplus.bigtop40.com/",
    "globalplayer": "https://www.winplus.globalplayer.com/",
}


def _headers() -> dict:
    return {"User-Agent": config.USER_AGENT, "Accept": "application/json, text/plain, */*"}


def extract_competition_id(url: str) -> int:
    """Pure. Raises ValueError if `url` doesn't look like a real Global WIN
    competition URL at all (no `/competition/<id>/` segment) — a
    same-shaped promotion/channel URL is the only kind this module is ever
    called with (see draft.py/submit.py's routing branch), so a mismatch
    here means something upstream is wrong, not something to guess past."""
    match = _COMPETITION_ID_RE.search(url)
    if not match:
        raise ValueError(f"could not find a /competition/<id>/ segment in {url!r}")
    return int(match.group(1))


def _resolve_homepage_for_competition(client: httpx.Client, comp_id: int) -> str:
    """A real competition's own `brands` array (from
    `/data/competitions/list.json`) plus `/data/init.json`'s brand-code map
    determines which real `winplus.<brand>` homepage actually features it
    (see module docstring). Resolves live at draft/submit time (two cheap
    extra API calls), not stored speculatively on `Promotion` at discovery
    time, since it's only ever needed here.

    Raises RuntimeError if `comp_id` isn't in the current listing at all,
    or if every brand it's tagged with maps to an unknown/unmapped brand
    code — refuses to guess a homepage rather than picking one at random."""
    init_resp = client.get(_INIT_URL, headers=_headers(), timeout=config.REQUEST_TIMEOUT_SECONDS)
    init_resp.raise_for_status()
    brands_by_code: dict = init_resp.json().get("brands", {})
    id_to_code = {b.get("id"): code for code, b in brands_by_code.items() if b.get("id") is not None}

    list_resp = client.get(_LIST_URL, headers=_headers(), timeout=config.REQUEST_TIMEOUT_SECONDS)
    list_resp.raise_for_status()
    listing: list[dict] = list_resp.json()
    item = next((i for i in listing if i.get("id") == comp_id), None)
    if item is None:
        raise RuntimeError(
            f"competition {comp_id} not found in Global WIN's own /data/competitions/list.json — "
            "can't resolve which brand homepage to use"
        )

    for brand_id in item.get("brands", []):
        code = id_to_code.get(brand_id)
        homepage = _BRAND_CODE_TO_HOMEPAGE.get(code) if code else None
        if homepage:
            return homepage

    raise RuntimeError(
        f"competition {comp_id} is only tagged with brand id(s) {item.get('brands')!r}, none of which "
        "resolves to a known winplus homepage (see _BRAND_CODE_TO_HOMEPAGE) — refusing to guess one"
    )


def sign_in(page) -> None:
    """Drives the real Global Player sign-in form in `page` — see module
    docstring for the field selectors/mechanics and why this, not
    `stations/global_win.py`'s `login()`, is used here. Raises
    RuntimeError immediately, before any navigation, if
    GLOBAL_PLAYER_EMAIL/PASSWORD are unset. Verifies the login actually
    succeeded (the URL moved away from `/signin/` within a bounded wait)
    before returning — never assumes success; on a timeout, raises with
    whatever text is visible in the sign-in form at that point, best-
    effort, since the real error-message markup was never observed (Global
    only renders it after a real failed submit, which this codebase must
    never trigger just to go looking for it)."""
    if not config.GLOBAL_PLAYER_EMAIL or not config.GLOBAL_PLAYER_PASSWORD:
        raise RuntimeError(
            "GLOBAL_PLAYER_EMAIL/GLOBAL_PLAYER_PASSWORD are not set. global_win_auth.sign_in() needs a real "
            "personal Global Player email+password (see docs/build-log.md for the accepted-risk note) — "
            "this codebase never invents or requests real credentials, so set these yourself before calling it."
        )

    page.goto(_SIGNIN_URL, timeout=30000)
    dismiss_consent_banner(page)

    page.fill("#email", config.GLOBAL_PLAYER_EMAIL)
    page.fill("#password", config.GLOBAL_PLAYER_PASSWORD)
    page.click('button[type="submit"]')

    try:
        page.wait_for_url(lambda url: "/signin/" not in url, timeout=15000)
    except Exception as exc:
        visible_text = ""
        try:
            visible_text = page.locator("form").first.inner_text(timeout=2000)
        except Exception:
            pass
        raise RuntimeError(
            f"Global Player sign-in did not appear to succeed — still on {page.url} 15s after submitting. "
            f"Visible form text at that point: {visible_text!r}"
        ) from exc

    logger.info("Global Player sign-in succeeded, landed on %s", page.url)


def _click_through_to_competition(page, comp_id: int) -> None:
    """The one seam `open_authenticated_page` uses to reach the target
    competition without ever calling `goto()` on its deep link directly
    (see module docstring for why). Matches by the competition's own
    numeric id inside the anchor's href — confirmed live 2026-09-28 that a
    real brand homepage's own rendered links use exactly this
    `/competition/<id>/<slug>` shape. Raises RuntimeError if no such link
    is found — refuses to fall back to a direct `goto()`, which is the
    specific path confirmed to crash Global's own frontend JS."""
    link = page.locator(f'a[href*="/competition/{comp_id}/"]').first
    if link.count() == 0:
        raise RuntimeError(
            f"no link to /competition/{comp_id}/ found on the resolved brand homepage ({page.url}) — "
            "refusing to fall back to a direct goto() of the deep link (confirmed live to crash Global's "
            "own frontend JS on a cold load, see module docstring)"
        )
    link.click(timeout=10000)
    page.wait_for_timeout(3000)  # let the SPA's client-side route transition finish rendering


@contextmanager
def open_authenticated_page(url: str):
    """Same shape as `browser.open_page()`: launch, sign in, navigate to
    the real entry form via the resolved brand homepage + in-app
    click-through (never a direct `goto()` of `url` itself — see module
    docstring), then yield the page once real content has loaded.

    Fresh sign-in every call — no session reuse across channels in one
    run, matching this codebase's "nothing persisted, fresh every time"
    posture elsewhere (Bauer's guest token, `stations/global_win.py`'s own
    `login()`) and the entry-execution job's real observed volume (rarely
    more than one Global WIN channel per run)."""
    comp_id = extract_competition_id(url)
    with httpx.Client() as client:
        homepage_url = _resolve_homepage_for_competition(client, comp_id)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=config.USER_AGENT)
        try:
            sign_in(page)
            page.goto(homepage_url, timeout=30000)
            dismiss_consent_banner(page)
            _click_through_to_competition(page, comp_id)
            yield page
        finally:
            browser.close()
