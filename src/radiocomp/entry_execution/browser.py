"""
Playwright page interaction: extracting a form's field structure to hand
to the LLM, applying a validated fill plan, and screenshotting.

extract_form_fields() deliberately does NOT hand the LLM raw HTML or a
screenshot — our own code resolves one definite, working selector per
field and pairs it with label/type/option text; the model only ever
classifies field *purpose* against selectors we already know work. Raw
HTML is noisier (framework wrapper divs, scripts) and invites a
hallucinated selector; a screenshot alone still can't produce a usable
CSS selector, so it doesn't save this step, it just adds an unreliable
hop before it. Every field is tagged with our own data-rc-field marker
rather than relying on the page's own id/name (which can contain
characters that need CSS-escaping, or be entirely absent) — deliberately
boring and always valid, over something that looks more "natural" but
needs escaping edge cases to be correct.
"""

from __future__ import annotations

import random
from contextlib import contextmanager

from .. import config

_SKIP_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image", "file"}

# The Sourcepoint cookie-consent idiom, confirmed working verbatim on both
# win.talksport.com (originally in stations/talksport_widget.py) and
# globalplayer.com/winplus.* (entry_execution/global_win_auth.py) — moved
# here so both can share one implementation rather than each keeping its
# own inline copy. Best-effort and silent: a page with no matching modal
# (or one whose modal doesn't match this markup) is a safe no-op, never an
# error — dismiss_consent_banner() is called unconditionally by open_page()
# below, on pages that may or may not have any consent modal at all.
_CONSENT_IFRAME_SELECTOR = 'iframe[id^="sp_message_iframe"]'


def dismiss_consent_banner(page, timeout: int = 5000) -> None:
    """Best-effort dismiss of a Sourcepoint cookie-consent modal, if one is
    present. Never raises — a page without a matching modal (or one that
    doesn't appear within `timeout`) is left exactly as it was."""
    try:
        page.frame_locator(_CONSENT_IFRAME_SELECTOR).get_by_role("button", name="Accept").first.click(
            timeout=timeout
        )
        page.wait_for_timeout(1000)
    except Exception:
        pass  # no consent modal this time, or it didn't match — proceed regardless


@contextmanager
def open_page(url: str):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=config.USER_AGENT)
        try:
            page.goto(url, timeout=30000)
            dismiss_consent_banner(page)
            yield page
        finally:
            browser.close()


def extract_form_fields(page) -> list[dict]:
    elements = page.query_selector_all("input, textarea, select")
    fields: list[dict] = []
    index = 0
    for el in elements:
        tag = el.evaluate("e => e.tagName.toLowerCase()")
        input_type = el.get_attribute("type") or {"textarea": "textarea", "select": "select"}.get(tag, "text")
        if input_type in _SKIP_INPUT_TYPES:
            continue

        marker = f"rc-field-{index}"
        el.evaluate("(e, m) => e.setAttribute('data-rc-field', m)", marker)
        selector = f'[data-rc-field="{marker}"]'

        options = None
        if tag == "select":
            options = el.eval_on_selector_all("option", "opts => opts.map(o => o.textContent.trim())")

        fields.append(
            {
                "selector": selector,
                "label": _resolve_label(page, el) or "(no label found)",
                "input_type": input_type,
                "options": options,
            }
        )
        index += 1

    # A Google Form's radio-button/checkbox questions are role="radio"/
    # role="checkbox" divs, not real <input>s — invisible to the
    # input/textarea/select scan above. Confirmed live (2026-09-30) against
    # two real talkSPORT competitions' embedded Google Forms: every
    # question's options (real inputs and these role-based ones alike)
    # share a single ancestor [role="listitem"] container — the same
    # boundary _resolve_label()'s own new fallback (below) uses — so that's
    # what this groups sibling options by, rather than Google's own
    # internal role="radiogroup" wrapper (present for radio questions on
    # both real fixtures, but never confirmed for a checkbox question,
    # since neither real form had one).
    index = _add_option_group_fields(page, fields, index)
    return fields


def _add_option_group_fields(page, fields: list[dict], index: int) -> int:
    option_elements = page.query_selector_all('[role="radio"], [role="checkbox"]')
    for opt_el in option_elements:
        container = opt_el.evaluate_handle(
            "e => e.closest('[role=\"listitem\"]') || e.parentElement"
        ).as_element()
        if container is None:
            continue
        if container.get_attribute("data-rc-field"):
            continue  # already turned into a field via an earlier sibling option in this same group

        role = opt_el.get_attribute("role")
        options = container.eval_on_selector_all(
            '[role="radio"], [role="checkbox"]',
            "els => els.map(e => (e.getAttribute('aria-label') || e.textContent || '').trim())",
        )

        marker = f"rc-field-{index}"
        container.evaluate("(e, m) => e.setAttribute('data-rc-field', m)", marker)
        selector = f'[data-rc-field="{marker}"]'

        label = container.evaluate(
            """e => {
                const li = e.closest('[role="listitem"]') || e;
                const h = li.querySelector('[role="heading"]');
                return h ? h.innerText : null;
            }"""
        )

        fields.append(
            {
                "selector": selector,
                "label": (label or "").strip() or "(no label found)",
                "input_type": role,
                "options": options,
            }
        )
        index += 1
    return index


def _resolve_label(page, el) -> str:
    el_id = el.get_attribute("id")
    if el_id:
        label_el = page.query_selector(f'label[for="{el_id}"]') if _is_safe_id(el_id) else None
        if label_el:
            text = label_el.inner_text().strip()
            if text:
                return text
    for attr in ("aria-label", "placeholder"):
        value = el.get_attribute(attr)
        # "Your answer" excluded deliberately: confirmed live (2026-09-30)
        # that a Google Form's own long-answer (<textarea>) question gets
        # this exact literal aria-label on every such field regardless of
        # the actual question text (the real Philadelphia-competition form
        # has one long-answer field whose question is "Address" — its
        # aria-label reads "Your answer" either way). Trusting it here
        # would produce exactly the kind of confident-looking-but-wrong
        # label this codebase's classifiers already avoid elsewhere — a
        # short, per-sub-field aria-label like "Day of the month"/"Month"/
        # "Year" (seen live on a date-of-birth field) is genuinely useful
        # and unaffected by this exclusion.
        if value and value.strip() and value.strip() != "Your answer":
            return value.strip()
    wrapping = el.evaluate("e => { const l = e.closest('label'); return l ? l.innerText : null; }")
    if wrapping and wrapping.strip():
        return wrapping.strip()

    # Google Forms fallback: confirmed live (2026-09-30) against two real
    # talkSPORT-embedded Google Forms that a field's question text is never
    # linked via id/label[for]/aria-label/a wrapping <label> at all (every
    # strategy above misses) — it lives in a separate [role="heading"] div,
    # sharing a single ancestor [role="listitem"] container with the actual
    # input. This only ever fires when every native strategy above has
    # already failed, so a normal HTML form's labels resolve exactly as
    # before.
    heading_text = el.evaluate(
        """e => {
            const li = e.closest('[role="listitem"]');
            if (!li) return null;
            const h = li.querySelector('[role="heading"]');
            return h ? h.innerText : null;
        }"""
    )
    if heading_text and heading_text.strip():
        return heading_text.strip()
    return ""


def _is_safe_id(value: str) -> bool:
    # Only used to build a `label[for="..."]` selector — refuse ids with
    # characters that would need CSS-escaping rather than trying to
    # escape them correctly ourselves.
    return all(c.isalnum() or c in "-_" for c in value)


def apply_fill_actions(page, actions: list[dict]) -> None:
    for action in actions:
        if action["type"] == "fill":
            page.fill(action["selector"], action["value"])
            page.wait_for_timeout(random.randint(300, 900))  # naturally varied pace, not machine-speed
        elif action["type"] == "check":
            page.check(action["selector"])
            page.wait_for_timeout(random.randint(200, 500))
        elif action["type"] == "leave_unchecked":
            pass  # deliberate no-op — never call uncheck(); we only ever intervene
            # positively (checking a required consent box), never negatively
        elif action["type"] == "select_option":
            _select_option(page, action["selector"], action["option_text"])
            page.wait_for_timeout(random.randint(200, 500))


def _select_option(page, selector: str, option_text: str) -> None:
    """Selects the one option fill_plan.py's LLM classification named as
    correct — never a blind default. A real gap found and fixed
    2026-09-30: an earlier version of this function clicked whichever
    option's text read "yes" for any Google Form radio/checkbox field,
    which is wrong for an eligibility question where "No" is the
    genuinely correct answer for an eligible entrant (e.g. "Are you an
    employee of the promoter?"). option_text always comes from
    MappedField.selected_option, which validate_mapping() has already
    confirmed is one of this field's own real, extracted options — never
    invented here or by the model.

    Works for a native <select> (page.select_option by visible label) and
    for a Google Form role="radio"/role="checkbox" option-group (our own
    data-rc-field marker on the question's [role="listitem"] container,
    see extract_form_fields()'s _add_option_group_fields()) — matched
    purely by clicking whichever descendant option's own text equals
    option_text. Raises if the named option can't be found on the page —
    refuses to guess a fallback, matching click_submit()'s own posture."""
    el = page.query_selector(selector)
    tag = el.evaluate("e => e.tagName.toLowerCase()") if el is not None else None
    if tag == "select":
        page.select_option(selector, label=option_text)
        return

    target = el.evaluate_handle(
        """(c, text) => {
            const opts = Array.from(c.querySelectorAll('[role="radio"], [role="checkbox"]'));
            return opts.find(o => (o.getAttribute('aria-label') || o.textContent || '').trim() === text) || null;
        }""",
        option_text,
    ).as_element()
    if target is None:
        raise RuntimeError(f"option {option_text!r} not found among the real options for {selector!r} on this page")
    target.click()


def click_submit(page) -> None:
    """Finds and clicks the form's submit control. Raises rather than
    guessing at an arbitrary clickable element if nothing obvious matches."""
    for selector in ('button[type="submit"]', 'input[type="submit"]', "form button"):
        el = page.query_selector(selector)
        if el:
            el.click()
            return

    # Google Forms fallback, confirmed live (2026-09-30) against two real
    # talkSPORT-embedded forms: the submit control is a <div role="button">
    # Submit</div> — matches none of the three selectors above. Both real
    # forms had exactly one div[role="button"] whose visible text is
    # exactly "Submit"; a "Clear form" button (also a div[role="button"],
    # present on both real forms) must never match.
    for candidate in page.query_selector_all('div[role="button"]'):
        if candidate.inner_text().strip() == "Submit":
            candidate.click()
            return

    raise RuntimeError("could not find a submit control on the page")


def screenshot(page, path: str) -> None:
    page.screenshot(path=path, full_page=True)
