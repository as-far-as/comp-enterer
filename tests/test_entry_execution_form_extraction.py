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

from playwright.sync_api import sync_playwright

from radiocomp.entry_execution.browser import extract_form_fields

FIXTURE = Path(__file__).parent / "fixtures" / "entry_execution" / "sample_entry_form.html"


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
