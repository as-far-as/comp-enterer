"""
Global Commercial (`comp.<brand>`) entry-execution companion — a
station-specific sibling to `global_win_auth.py`, scoped to
entry-execution rather than discovery. See `stations/global_commercial.py`'s
own docstring for the platform background and the embedded-flight-data
parsing this module reuses from there.

Materially simpler than `global_win_auth.py`: there's no homepage-
resolution/click-through dance needed at all — login happens *inline* on
the competition page itself (a tabbed Gigya sign-up/sign-in widget), so
`open_authenticated_page()` just navigates straight to the competition's
own URL.

**Live-confirmed mechanics (2026-10-05/06, against the one real,
currently-live competition this module was built against,
https://comp.smoothradio.com/nescafe-2026/8 — never submitted, never
logged in for real, no credentials exist in this environment — see
below):**

1. A direct `page.goto()` on the competition's own URL loads cleanly,
   zero JS errors (no Global-WIN-style cold-load crash — this really is
   an ordinary Next.js page, unlike winplus's SPA). The existing
   `dismiss_consent_banner()` (entry_execution/browser.py) works here
   unmodified.
2. The login form is reached by first clicking the "Log In" tab
   (`#select-login`) inside the page's own embedded Gigya widget
   (`#gigya-login`) — "Sign Up" is the default-active tab. **A plain
   Playwright `click()` on this tab is unreliable and must not be used**:
   `#select-login` itself (an `<li>` in a float-based tab layout) has a
   real zero-height bounding box, which Playwright refuses to click at
   all ("element is not visible"); its `<a>` child does have a real
   clickable area, but a page-position click there — even with
   `force=True` — lands on a sticky page footer that visually overlaps
   this part of the page instead of the tab (confirmed by checking the
   tab's own "active" CSS class before/after: it never changed either
   way). The one mechanism confirmed live to actually work is a real,
   trusted `.click()` dispatched directly on the anchor DOM node via
   `page.locator(...).evaluate("el => el.click()")` — this bypasses
   Playwright's own position-based hit-testing entirely, invoking the
   click handler regardless of what's visually on top, and was confirmed
   (via the same before/after "active"-class check) to reliably flip the
   tab. Once the tab is active, `#login input[name="email"]`,
   `#login input[name="password"]`, and `#login button[type="submit"]`
   all become genuinely visible/interactable (confirmed live).
3. The tie-breaker question/options render **pre-login**, confirmed live
   as: `<label for="answer">`, a single shared
   `<input type="hidden" name="answer" value="">`, and (scoped, confirmed
   live, to a `.section__mechanic` wrapping container — there were
   exactly 3 such buttons on the whole real page, all inside it) a `<ul>`
   of `<li><button type="button">...<span>OptionText</span></button></li>`
   per answer. These buttons carry no ARIA role at all (confirmed
   live) — so they're invisible to `browser.py`'s own
   `extract_form_fields()` scan (which only looks at real
   `input`/`textarea`/`select` elements, plus `role="radio"`/
   `role="checkbox"` groups) both before and after being answered; the
   hidden `input[name="answer"]` itself is also skipped there (hidden
   inputs are explicitly excluded). So by the time `draft.py`'s generic
   field-mapping step runs, this question is completely out of its view —
   already resolved, never something the LLM sees or classifies. Clicking
   the option matching the real `correctAnswer` text was confirmed live
   to populate the hidden input with that exact text (e.g. clicking
   "Matilda" populating `input[name="answer"]` with `value="Matilda"`).

**The leaked-answer decision — stated plainly, as the user's own
explicit, deliberate choice, not an inference made on their behalf:**
this platform's own page exposes the tie-breaker's correct answer in
plain, unauthenticated JSON (`entryMultipleChoice.correctAnswer`,
confirmed live to be a real field, not a guess). The user has chosen,
directly and knowingly, to have this module use that leaked field to
auto-select the right answer button, rather than treating this
multiple-choice question the way every other creative/skill-based
tie-breaker in this codebase is treated (flagged for manual input, never
auto-filled — see `entry_execution/fill_plan.py`'s `CREATIVE_FREETEXT`
classification). This is a real, consequential call: it's the reason
this one source can go all the way through end-to-end submission rather
than draft-and-flag, and it rests entirely on trusting that the
platform's own leaked field is genuinely correct. `_answer_tiebreaker()`
below implements exactly this, and raises rather than guessing if the
field is ever missing or if the matching answer button can't be found —
it never falls back to picking an option blind.

**The real first login is deliberately not something this module, or any
agent, does unsupervised** — same posture as `global_win_auth.py`.
`config.GLOBAL_COMMERCIAL_EMAIL`/`GLOBAL_COMMERCIAL_PASSWORD` are real
Secret Manager secrets the user creates themselves (never typed in by an
agent); `sign_in()` raises `RuntimeError` immediately if either is unset,
before ever touching the login form (tab click, fill, or submit) — the
preceding `page.goto()`/consent-dismiss in `open_authenticated_page()` is
the same safe, anonymous page load discovery itself already performs,
carrying no credential risk. Every mechanic in this module short of a
real login (tab click, field selectors, tie-breaker click/hidden-input
population) was verified live against the real site, as described above;
the post-submit "did sign-in actually succeed" check below
(`_STEP_SELECTOR` leaving its known pre-login value) was **not** verified
against a real successful login — no real credentials have ever been
exercised against this live site while building this module — so if a
real login succeeds but this check still doesn't recognise it, that
assumption needs re-examining against what's actually observed, not
patched blind. The real first submission, with real credentials, is the
user's own action, later, watched — see docs/build-log.md.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from .. import config
from .browser import dismiss_consent_banner

logger = logging.getLogger(__name__)

_LOGIN_TAB_SELECTOR = "#select-login a"
_EMAIL_SELECTOR = '#login input[name="email"]'
_PASSWORD_SELECTOR = '#login input[name="password"]'
_SUBMIT_SELECTOR = '#login button[type="submit"]'

# Confirmed live (2026-10-05/06): the Gigya widget's own step-tracking container
# (`<div step="UnAuthenticated">`) sits inside #gigya-login. Never confirmed what
# value it takes on a real successful login (see module docstring) — sign_in() below
# only ever checks that it's left this one known pre-login value, not what it becomes.
_STEP_SELECTOR = "#gigya-login [step]"
_PRE_LOGIN_STEP_VALUE = "UnAuthenticated"

# Confirmed live scoping container for the tie-breaker's answer buttons — see module
# docstring. Matched exactly 3 real option buttons, and nothing else on the page.
_ANSWER_OPTION_SELECTOR = ".section__mechanic ul li button"
_HIDDEN_ANSWER_SELECTOR = 'input[type="hidden"][name="answer"]'


def sign_in(page) -> None:
    """Drives the real inline Gigya login widget on `page` (already navigated to the
    target competition URL by the caller) — see module docstring for the field
    selectors/mechanics and the real tab-click quirk this works around. Raises
    RuntimeError immediately, before touching the login form at all, if
    GLOBAL_COMMERCIAL_EMAIL/PASSWORD are unset. Verifies sign-in actually succeeded
    (the Gigya step attribute moves away from its known pre-login value, within a
    bounded wait) before returning — never assumes success; see module docstring for
    the real, documented gap in what "moved away" was actually confirmed against."""
    if not config.GLOBAL_COMMERCIAL_EMAIL or not config.GLOBAL_COMMERCIAL_PASSWORD:
        raise RuntimeError(
            "GLOBAL_COMMERCIAL_EMAIL/GLOBAL_COMMERCIAL_PASSWORD are not set. "
            "global_commercial_auth.sign_in() needs a real personal Global Commercial "
            "(comp.<brand>) email+password — this codebase never invents or requests real "
            "credentials, so set these yourself before calling it."
        )

    # See module docstring: a position-based Playwright click here (even force=True)
    # is confirmed live to be unreliable (a zero-height <li>, and a sticky footer
    # intercepting its <a> child) — a real DOM .click() dispatched directly on the
    # node is the one mechanism confirmed to actually flip the tab.
    page.locator(_LOGIN_TAB_SELECTOR).evaluate("el => el.click()")
    page.locator(_EMAIL_SELECTOR).wait_for(state="visible", timeout=10000)

    page.fill(_EMAIL_SELECTOR, config.GLOBAL_COMMERCIAL_EMAIL)
    page.fill(_PASSWORD_SELECTOR, config.GLOBAL_COMMERCIAL_PASSWORD)
    page.click(_SUBMIT_SELECTOR)

    try:
        page.wait_for_function(
            "sel => { const el = document.querySelector(sel); "
            "return !!el && el.getAttribute('step') !== 'UnAuthenticated'; }",
            arg=_STEP_SELECTOR,
            timeout=15000,
        )
    except Exception as exc:
        visible_text = ""
        try:
            visible_text = page.locator("#login").first.inner_text(timeout=2000)
        except Exception:
            pass
        raise RuntimeError(
            f"Global Commercial sign-in did not appear to succeed — the Gigya step attribute "
            f"({_STEP_SELECTOR}) never left its pre-login value ({_PRE_LOGIN_STEP_VALUE!r}) within "
            f"15s of submitting. Visible #login text at that point: {visible_text!r}. NOTE: the real "
            f"post-login step value has never actually been observed (no real credentials have been "
            f"exercised against this live site while building this module — see module docstring)."
        ) from exc

    logger.info("Global Commercial sign-in appeared to succeed (step attribute left %r)", _PRE_LOGIN_STEP_VALUE)


def _answer_tiebreaker(page) -> None:
    """Re-reads the current page's own embedded competition JSON (via
    `stations.global_commercial.extract_competition_json`, against `page.content()` —
    confirmed live that the flight-data script tags survive client-side hydration
    unchanged) for the real `correctAnswer`, finds the matching answer button by its
    visible text, and clicks it. See module docstring for the leaked-answer decision
    this implements. Raises rather than guessing if entryMultipleChoice/correctAnswer
    is missing, or if no button's text matches it, or if clicking it doesn't populate
    the hidden input as expected — never falls back to picking an option blind.
    A no-op (logged, not raised) if this particular page's entryMechanic isn't
    entryMultipleChoice at all — nothing here to auto-answer."""
    from ..stations import global_commercial

    doc = global_commercial.extract_competition_json(page.content())
    if doc is None or doc.get("entryMechanic") != "entryMultipleChoice":
        logger.info("No entryMultipleChoice tie-breaker found on %s — nothing to auto-answer", page.url)
        return

    entry_mc = doc.get("entryMultipleChoice") or {}
    correct_answer = entry_mc.get("correctAnswer")
    if not correct_answer:
        raise RuntimeError(
            "entryMechanic is entryMultipleChoice but no correctAnswer field was found in the "
            "embedded competition JSON — refusing to guess which option to click"
        )

    options = page.locator(_ANSWER_OPTION_SELECTOR)
    target = None
    for i in range(options.count()):
        if options.nth(i).inner_text().strip() == correct_answer:
            target = options.nth(i)
            break
    if target is None:
        raise RuntimeError(
            f"no answer button matching the known-correct option {correct_answer!r} was found among "
            f"{options.count()} real option button(s) on the page"
        )

    target.click(timeout=10000)

    try:
        page.wait_for_function(
            "sel => !!document.querySelector(sel)?.value",
            arg=_HIDDEN_ANSWER_SELECTOR,
            timeout=5000,
        )
    except Exception as exc:
        raise RuntimeError(
            f"clicked the {correct_answer!r} answer button but the hidden "
            f"{_HIDDEN_ANSWER_SELECTOR} input never got a value"
        ) from exc

    actual_value = page.locator(_HIDDEN_ANSWER_SELECTOR).get_attribute("value")
    if actual_value != correct_answer:
        raise RuntimeError(
            f"clicked the {correct_answer!r} answer button but the hidden input ended up with "
            f"{actual_value!r} instead — refusing to proceed with a mismatched answer"
        )

    logger.info("Global Commercial tie-breaker answered: %r", correct_answer)


@contextmanager
def open_authenticated_page(url: str):
    """Launch, navigate straight to the competition's own URL (no homepage/
    click-through resolution needed, unlike Global WIN — see module docstring),
    dismiss consent, sign in, then auto-answer the tie-breaker — all before yielding
    the page, so by the time draft.py's generic extract_form_fields() runs, the
    question is already resolved and out of its view (see module docstring).

    Fresh sign-in every call — no session reuse across channels in one run, same
    "nothing persisted, fresh every time" posture as global_win_auth.py's own
    open_authenticated_page()."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=config.USER_AGENT)
        try:
            page.goto(url, timeout=30000)
            dismiss_consent_banner(page)
            sign_in(page)
            _answer_tiebreaker(page)
            yield page
        finally:
            browser.close()
