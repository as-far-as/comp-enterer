"""
Offline, always-run: browser.extract_form_fields() against a hand-built,
realistic fixture form (not scraped from a real live site — none of the 4
currently-discovered promotions have a qualifying web_form channel, and
hitting a real site's form repeatedly under automated test runs cuts
against this project's own polite-crawling stance). No LLM call here —
see test_entry_execution_live.py for the one genuinely live piece.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from radiocomp.entry_execution.browser import apply_fill_actions, extract_form_fields

FIXTURE = Path(__file__).parent / "fixtures" / "entry_execution" / "sample_entry_form.html"

# A real Google Form, captured live (`page.content()` after real
# rendering, 2026-09-30) from the actual form embedded in talkSPORT's
# "WIN a trip to Philadelphia for two" competition — same file://-fixture
# technique as sample_entry_form.html/clean_entry_form.html above, just a
# real captured DOM snapshot rather than hand-built HTML. Static, so no
# live Google Forms JS runs against it (clicking still resolves the right
# element — see test_google_form_check_action_clicks_the_yes_option below
# — but has no visible aria-checked effect, which is a limit of testing
# against a frozen snapshot, not something this suite depends on).
GOOGLE_FORM_FIXTURE = Path(__file__).parent / "fixtures" / "entry_execution" / "google_form_philadelphia.html"


def _extract_fields() -> list[dict]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{FIXTURE.resolve()}")
        fields = extract_form_fields(page)
        browser.close()
    return fields


def test_extracts_every_real_field_and_skips_the_submit_button():
    fields = _extract_fields()
    # 8 real inputs in the fixture; the submit <button> must not appear —
    # extract_form_fields only walks input/textarea/select.
    assert len(fields) == 8


def test_every_selector_is_unique_and_actually_usable():
    # Selectors must resolve within the *same* page session they were
    # extracted on — the data-rc-field markers extract_form_fields() sets
    # are DOM mutations, so they don't survive a fresh navigation. This is
    # exactly why submit.py must call extract_form_fields() again on its
    # freshly-navigated page (re-tagging fields in the same deterministic
    # DOM order) before checking a saved plan's selectors still resolve —
    # never check a saved selector against an untagged fresh page.
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{FIXTURE.resolve()}")
        fields = extract_form_fields(page)
        selectors = [f["selector"] for f in fields]
        assert len(selectors) == len(set(selectors))
        for f in fields:
            assert page.locator(f["selector"]).count() == 1, f["selector"]
        browser.close()


def test_labels_resolve_for_every_field_type():
    fields = _extract_fields()
    by_label = {f["label"]: f for f in fields}

    assert "Full name" in by_label
    assert by_label["Full name"]["input_type"] == "text"

    assert "Email address" in by_label
    assert by_label["Email address"]["input_type"] == "email"

    # Checkbox labels come from the wrapping <label> ancestor, not label[for]
    assert "I am 18 or over and agree to the competition terms and conditions" in by_label
    assert by_label["I am 18 or over and agree to the competition terms and conditions"]["input_type"] == "checkbox"

    assert "Keep me updated with offers and news from our partners" in by_label

    # The full tie-breaker question text is the label — this is exactly
    # what llm_mapping.py needs to see to classify it as creative_freetext
    assert "In 25 words or fewer, tell us why you deserve to win this break" in by_label
    assert by_label["In 25 words or fewer, tell us why you deserve to win this break"]["input_type"] == "textarea"


def test_re_extraction_on_a_fresh_page_reassigns_the_same_markers():
    # The concrete property submit.py's safety re-check depends on: as
    # long as the form's structure is unchanged, extract_form_fields()
    # deterministically assigns "rc-field-0", "rc-field-1", ... in the
    # same DOM order every time, on a completely fresh page load — this is
    # what lets a fill_plan saved at draft time still resolve correctly
    # after a real re-navigation at submit time.
    first = _extract_fields()
    second = _extract_fields()
    assert [f["selector"] for f in first] == [f["selector"] for f in second]
    assert [f["label"] for f in first] == [f["label"] for f in second]


def test_no_field_is_none_or_empty_label():
    fields = _extract_fields()
    for f in fields:
        assert f["label"], f["selector"]


# --- real embedded Google Form: radio questions, div-based submit ---------


def _extract_google_form_fields():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{GOOGLE_FORM_FIXTURE.resolve()}")
        fields = extract_form_fields(page)
        browser.close()
    return fields


def test_google_form_native_text_and_textarea_fields_still_get_the_right_label():
    # Confirmed live: a Google Form's own text/textarea inputs carry none
    # of id/label[for]/aria-label/wrapping-<label> — every existing
    # _resolve_label() strategy misses, so this exercises the new
    # [role="listitem"] -> [role="heading"] fallback exclusively.
    fields = _extract_google_form_fields()
    by_label = {f["label"]: f for f in fields}

    assert "Full name" in by_label
    assert by_label["Full name"]["input_type"] == "text"
    assert "Email" in by_label
    assert "Contact Number" in by_label
    # The long-answer field's aria-label reads the generic, non-per-field
    # "Your answer" on every Google Form — confirmed live this must be
    # excluded so the real question text ("Address") is used instead.
    assert "Address" in by_label
    assert by_label["Address"]["input_type"] == "textarea"
    assert "Your answer" not in by_label


def test_google_form_radio_question_is_found_with_its_real_options():
    fields = _extract_google_form_fields()
    radio_fields = [f for f in fields if f["input_type"] == "radio"]
    assert len(radio_fields) == 1
    field = radio_fields[0]
    assert "Hawksbee & Jac" in field["label"]
    assert field["options"] == ["Yes", "No"]


def test_google_form_selectors_are_unique_and_actually_usable():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{GOOGLE_FORM_FIXTURE.resolve()}")
        fields = extract_form_fields(page)
        selectors = [f["selector"] for f in fields]
        assert len(selectors) == len(set(selectors))
        for f in fields:
            assert page.locator(f["selector"]).count() == 1, f["selector"]
        browser.close()


def _install_click_recorder(page) -> None:
    """The frozen Google Form fixture's own JS doesn't run offline (no
    live backend, no React re-render), so a real click doesn't toggle
    aria-checked the way it would on the live page — this records which
    element actually received the native browser click event instead,
    which Playwright's .click() fires regardless of whether the page's
    own JS reacts to it. A robust way to prove *which specific* option
    was clicked without depending on the fixture's (non-functional,
    offline) visual state update."""
    page.evaluate(
        """() => {
            window.__rc_clicked = [];
            document.addEventListener('click', (e) => {
                const opt = e.target.closest('[role="radio"], [role="checkbox"]');
                if (opt) {
                    window.__rc_clicked.push((opt.getAttribute('aria-label') || opt.textContent || '').trim());
                }
            }, true);
        }"""
    )


def _clicked_options(page) -> list[str]:
    return page.evaluate("() => window.__rc_clicked || []")


def test_select_option_action_picks_the_named_option_not_a_default():
    # A real gap found and fixed 2026-09-30: page.check() only works on a
    # real checkable <input> and would raise against our own
    # group-container marker; an earlier version of this code instead
    # always clicked whichever option's text read "yes", which is wrong
    # whenever the correct answer for this specific question is "No" (see
    # fill_plan.py's option_group classification). select_option must pick
    # exactly the option it's told to, in either direction.
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{GOOGLE_FORM_FIXTURE.resolve()}")
        fields = extract_form_fields(page)
        radio_field = next(f for f in fields if f["input_type"] == "radio")
        _install_click_recorder(page)

        apply_fill_actions(page, [{"type": "select_option", "selector": radio_field["selector"], "option_text": "No"}])

        assert _clicked_options(page) == ["No"]
        browser.close()


def test_select_option_action_can_pick_yes_too():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{GOOGLE_FORM_FIXTURE.resolve()}")
        fields = extract_form_fields(page)
        radio_field = next(f for f in fields if f["input_type"] == "radio")
        _install_click_recorder(page)

        apply_fill_actions(
            page, [{"type": "select_option", "selector": radio_field["selector"], "option_text": "Yes"}]
        )

        assert _clicked_options(page) == ["Yes"]
        browser.close()


def test_select_option_action_raises_for_an_option_text_not_on_the_page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{GOOGLE_FORM_FIXTURE.resolve()}")
        fields = extract_form_fields(page)
        radio_field = next(f for f in fields if f["input_type"] == "radio")

        with pytest.raises(RuntimeError, match="not found"):
            apply_fill_actions(
                page, [{"type": "select_option", "selector": radio_field["selector"], "option_text": "Maybe"}]
            )
        browser.close()


def test_google_form_submit_control_selector_matches_submit_only_not_clear_form():
    # click_submit()'s Google Forms fallback matches the div[role="button"]
    # whose visible text is exactly "Submit", never "Clear form" (also a
    # div[role="button"] on the real form). This test deliberately proves
    # that matching logic — the same selector/predicate click_submit()
    # itself uses — without ever actually clicking a Google Form's submit
    # control, offline fixture or otherwise: this project's hard safety
    # rule is to never click that control anywhere, in any test, even
    # against a frozen, disconnected file:// snapshot with no real
    # backend to submit to.
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{GOOGLE_FORM_FIXTURE.resolve()}")

        candidates = page.query_selector_all('div[role="button"]')
        submit_matches = [c for c in candidates if c.inner_text().strip() == "Submit"]
        clear_form_matches = [c for c in candidates if c.inner_text().strip() == "Clear form"]

        assert len(submit_matches) == 1
        assert len(clear_form_matches) == 1  # confirms the fixture genuinely has both, not just one
        browser.close()
