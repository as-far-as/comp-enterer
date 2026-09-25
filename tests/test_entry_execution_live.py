"""
The one genuinely live piece of the entry-execution engine: a real Gemini
call against the fixture form (tests/fixtures/entry_execution/sample_entry_form.html),
asserting structural properties a sane mapping must have — not exact
wording, since the model's classification reasoning can phrase things
differently run to run.

Skipped unless GEMINI_API_KEY is set — this makes a real API call and is
not part of the default offline test run.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="live Gemini API call — set GEMINI_API_KEY to run",
)

from radiocomp.entry_execution import browser, llm_mapping
from radiocomp.entry_execution.fill_plan import FieldClassification, validate_mapping

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "entry_execution" / "sample_entry_form.html"


def test_live_mapping_classifies_the_fixture_form_sanely():
    url = f"file://{FIXTURE_PATH.resolve()}"
    with browser.open_page(url) as page:
        fields = browser.extract_form_fields(page)

    raw = llm_mapping.request_field_mapping(fields)
    mapping = validate_mapping(raw, known_selectors={f["selector"] for f in fields})

    by_label = {f.field_label: f for f in mapping.fields}

    profile_field_names = {
        f.profile_field for f in mapping.fields if f.classification == FieldClassification.PROFILE_FIELD
    }
    assert {"name", "email", "phone", "date_of_birth", "address"} <= profile_field_names

    creative = [f for f in mapping.fields if f.classification == FieldClassification.CREATIVE_FREETEXT]
    assert len(creative) == 1
    assert "25 words" in creative[0].field_label or "why you deserve" in creative[0].field_label.lower()

    checkboxes = [f for f in mapping.fields if f.classification == FieldClassification.CHECKBOX]
    assert len(checkboxes) == 2
    for f in checkboxes:
        label_lower = f.field_label.lower()
        if "offer" in label_lower or "market" in label_lower or "news" in label_lower:
            assert f.checkbox_action.value == "leave_unchecked"
        else:
            assert f.checkbox_action.value == "check"
