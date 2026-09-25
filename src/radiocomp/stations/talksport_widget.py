"""
talkSPORT-specific fix for the "Online" entry channel's stuck-ambiguous
classification (is_free_route=None, review_recommended=True) — 7 of 9
real discovered web_form channels sit here (2026-09-08), because the
actual entry pricing isn't on the competition page's own static HTML at
all: it's delegated to a third-party competition-entry platform
(win.talksport.com) loaded via a cross-origin iframe.

This is deliberately NOT a generic "render the page with Playwright"
fix (an earlier version of this module tried exactly that, re-running
talksport.py's own parse_detail() against a rendered copy of the SAME
page — real-data testing proved that finds nothing new, since the price
was never on that page to begin with, rendered or not). Reaching the
real number needs three talkSPORT-platform-specific steps, each
confirmed live against a real competition before being written here:

1. Use config.USER_AGENT explicitly, not Playwright's default. This
   project's polite, self-identifying bot UA reliably got the widget
   iframe into the DOM (5/5 real attempts); Chromium's default headless
   UA got it into the DOM 0/6 times — something in the site's own
   ad-tech/bot-detection logic evidently treats a generic "HeadlessChrome"
   UA differently. What looked at first like non-deterministic flakiness
   in the widget's appearance was actually just this.
2. The widget iframe (`<iframe class="authenticated-iframe" loading="lazy">`)
   uses the browser's native lazy-loading — Chromium won't fetch it at
   all until it's scrolled into view. A Sourcepoint cookie-consent modal
   (`iframe[id^="sp_message_iframe"]`) sometimes also sits in front of
   it; dismissed best-effort since it isn't always present.
3. The widget's own rendered text uses a completely different phrasing
   convention from the outer page's classifier ("£X PER ENTRY" / "YOUR
   TOTAL : £X", not "charged at £X") — confirmed live for one real
   competition: "£2.50 PER ENTRY", "£2.50 · x1", "£10 · x5", "£20 · x20",
   "£30 · 100", "YOUR TOTAL : £2.50". That competition resolves to
   confidently PAID, not free — it's plausible this pricing-tier UI is a
   shared template across the whole platform, so most or all of the
   other 6 ambiguous channels may also resolve to paid rather than free.
   The value holds either way: a correctly-audited "paid" beats a
   permanently-ambiguous "unknown."

Same "never guess" posture as every other classifier in this codebase:
if the widget never appears, or its text doesn't match a known pattern,
the channel is left exactly as ambiguous as it started — never a
confident-looking wrong answer.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from ..models import EntryChannel

logger = logging.getLogger(__name__)

_CONSENT_IFRAME_SELECTOR = 'iframe[id^="sp_message_iframe"]'
_WIDGET_IFRAME_SELECTOR = "iframe.authenticated-iframe"
_WIDGET_DOMAIN_HINT = "win.talksport.com"

_PRICE_RE = re.compile(r"£\s?([\d,]+(?:\.\d+)?)\s*(?:per entry)", re.IGNORECASE)
# Matches the confirmed real pattern ("£2.50 PER ENTRY") specifically —
# deliberately not a bare £-amount match, to avoid picking up an
# unrelated figure (e.g. a prize value) that might also appear in the
# widget's own text.
_FREE_INDICATOR_RE = re.compile(r"\bfree\s+(?:to\s+)?enter\b|\bno\s+purchase\s+necessary\b", re.IGNORECASE)
# Unverified against any real free-widget example — none has been seen
# yet (see module docstring: it's plausible none of the 7 resolve to
# free at all). Fails safe: if a genuinely free widget phrases it
# differently, the channel just stays ambiguous rather than getting
# misclassified.


_DEFAULT_ATTEMPTS = 3


def fetch_widget_text(url: str, attempts: int = _DEFAULT_ATTEMPTS) -> Optional[str]:
    """None if the widget iframe never appears/attaches across all
    `attempts` tries. Confirmed live (2026-09-08) that a single attempt
    has a real, meaningful failure rate independent of wait time — even a
    15-second explicit wait_for_selector didn't help on a URL that had
    worked minutes earlier, so this isn't a "wait longer" problem, it's
    genuine intermittency (site-side A/B testing, session state, or
    anti-scraping behaviour — cause unconfirmed). Retrying with a fresh
    browser launch each time meaningfully improves the odds without
    pretending a single try is reliable. Only the last attempt's
    exception (if that try itself errors, not just returns "not found")
    propagates to the caller — an exception on an earlier attempt is
    treated the same as a "didn't appear" and retried."""
    last_exc: Optional[Exception] = None
    for _ in range(attempts):
        try:
            text = _fetch_widget_text_once(url)
        except Exception as exc:
            last_exc = exc
            continue
        if text is not None:
            return text
        last_exc = None
    if last_exc is not None:
        raise last_exc
    return None


def _fetch_widget_text_once(url: str) -> Optional[str]:
    """A single attempt — None if the widget iframe never appears/attaches
    this time (consent modal not dismissable, lazy-load didn't trigger,
    page structure differs) — never raises for that case, only for a
    genuine Playwright/browser-level failure. See fetch_widget_text() for
    the retry wrapper this project actually calls."""
    from playwright.sync_api import sync_playwright

    from .. import config

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=config.USER_AGENT)
        try:
            page.goto(url, timeout=30000)
            page.wait_for_timeout(2000)
            try:
                page.frame_locator(_CONSENT_IFRAME_SELECTOR).get_by_role(
                    "button", name="Accept"
                ).first.click(timeout=5000)
                page.wait_for_timeout(1000)
            except Exception:
                pass  # no consent modal this time, or it didn't match — proceed regardless

            widget_el = page.locator(_WIDGET_IFRAME_SELECTOR)
            if widget_el.count() == 0:
                return None
            widget_el.first.scroll_into_view_if_needed(timeout=5000)
            page.wait_for_timeout(3000)

            target = next((f for f in page.frames if _WIDGET_DOMAIN_HINT in f.url), None)
            if target is None:
                return None
            return target.locator("body").inner_text(timeout=5000)
        finally:
            browser.close()


def classify_widget_text(text: str) -> tuple[Optional[bool], Optional[float]]:
    """Pure. Returns (is_free_route, cost_to_entrant_gbp) — (None, None)
    if the widget's text doesn't match a known pattern at all, which the
    caller treats exactly like "couldn't determine": leave the channel
    ambiguous, never guess."""
    price_match = _PRICE_RE.search(text)
    if price_match:
        return False, float(price_match.group(1).replace(",", ""))
    if _FREE_INDICATOR_RE.search(text):
        return True, 0.0
    return None, None


def resolve_online_channel(url: str, static_channel: EntryChannel) -> EntryChannel:
    """The one seam ingest() calls for an ambiguous WEB_FORM channel.
    Never raises — falls back to static_channel unchanged on any failure
    (fetch exception, widget never appearing, or text that doesn't match
    a known pattern), logged at the appropriate level so a real failure
    is distinguishable from a legitimate "couldn't resolve" in the logs."""
    try:
        text = fetch_widget_text(url)
    except Exception as exc:
        logger.warning("Widget fetch failed for %s: %s — keeping static classification", url, exc)
        return static_channel

    if text is None:
        logger.info("Widget never appeared for %s — keeping static classification", url)
        return static_channel

    is_free, cost = classify_widget_text(text)
    if is_free is None:
        logger.info("Widget loaded for %s but text matched no known pattern — keeping static classification", url)
        return static_channel

    return static_channel.model_copy(
        update={
            "is_free_route": is_free,
            "cost_to_entrant_gbp": cost,
            "review_recommended": False,
            "raw_excerpt": text[:400],
        }
    )
