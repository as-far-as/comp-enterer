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
    return fields


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
        if value and value.strip():
            return value.strip()
    wrapping = el.evaluate("e => { const l = e.closest('label'); return l ? l.innerText : null; }")
    if wrapping and wrapping.strip():
        return wrapping.strip()
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


def click_submit(page) -> None:
    """Finds and clicks the form's submit control. Raises rather than
    guessing at an arbitrary clickable element if nothing obvious matches."""
    for selector in ('button[type="submit"]', 'input[type="submit"]', "form button"):
        el = page.query_selector(selector)
        if el:
            el.click()
            return
    raise RuntimeError("could not find a submit control on the page")


def screenshot(page, path: str) -> None:
    page.screenshot(path=path, full_page=True)
