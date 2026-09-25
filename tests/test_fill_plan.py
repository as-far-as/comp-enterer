from __future__ import annotations

from datetime import date

import pytest

from radiocomp.entry_execution.fill_plan import (
    build_fill_actions,
    needs_manual_input,
    validate_mapping,
)
from radiocomp.models import UserProfile


def _profile() -> UserProfile:
    return UserProfile(
        name="Jane Doe",
        date_of_birth=date(1990, 1, 1),
        address="1 Test Street, Testville, TE5 7ST",
        phone="07700900000",
        email="jane@example.com",
    )


def test_clean_profile_and_checkbox_form_validates_and_builds_actions():
    raw = {
        "fields": [
            {"selector": "#name", "field_label": "Full name", "classification": "profile_field", "profile_field": "name"},
            {"selector": "#email", "field_label": "Email", "classification": "profile_field", "profile_field": "email"},
            {
                "selector": "#terms",
                "field_label": "I agree to the T&Cs",
                "classification": "checkbox",
                "checkbox_action": "check",
            },
            {
                "selector": "#marketing",
                "field_label": "Send me offers",
                "classification": "checkbox",
                "checkbox_action": "leave_unchecked",
            },
        ]
    }
    known = {"#name", "#email", "#terms", "#marketing"}
    mapping = validate_mapping(raw, known)

    assert needs_manual_input(mapping) is False

    actions = build_fill_actions(mapping, _profile())
    by_selector = {a["selector"]: a for a in actions}
    assert by_selector["#name"] == {"type": "fill", "selector": "#name", "value": "Jane Doe"}
    assert by_selector["#email"] == {"type": "fill", "selector": "#email", "value": "jane@example.com"}
    assert by_selector["#terms"]["type"] == "check"
    assert by_selector["#marketing"]["type"] == "leave_unchecked"


def test_creative_freetext_field_means_manual_input_needed():
    raw = {
        "fields": [
            {"selector": "#name", "field_label": "Name", "classification": "profile_field", "profile_field": "name"},
            {
                "selector": "#tiebreaker",
                "field_label": "In 25 words, tell us why you deserve to win",
                "classification": "creative_freetext",
            },
        ]
    }
    mapping = validate_mapping(raw, {"#name", "#tiebreaker"})
    assert needs_manual_input(mapping) is True


def test_unmappable_field_means_manual_input_needed():
    raw = {
        "fields": [
            {"selector": "#favourite_station", "field_label": "Favourite station", "classification": "unmappable"},
        ]
    }
    mapping = validate_mapping(raw, {"#favourite_station"})
    assert needs_manual_input(mapping) is True


def test_invented_selector_is_rejected():
    raw = {
        "fields": [
            {"selector": "#not-a-real-field", "field_label": "x", "classification": "profile_field", "profile_field": "name"},
        ]
    }
    with pytest.raises(ValueError, match="not among the fields we sent"):
        validate_mapping(raw, known_selectors={"#name"})


def test_duplicate_selector_is_rejected():
    raw = {
        "fields": [
            {"selector": "#name", "field_label": "a", "classification": "profile_field", "profile_field": "name"},
            {"selector": "#name", "field_label": "b", "classification": "profile_field", "profile_field": "email"},
        ]
    }
    with pytest.raises(ValueError, match="duplicate selector"):
        validate_mapping(raw, known_selectors={"#name"})


def test_field_count_mismatch_is_rejected():
    raw = {
        "fields": [
            {"selector": "#name", "field_label": "a", "classification": "profile_field", "profile_field": "name"},
        ]
    }
    with pytest.raises(ValueError, match="expected 2 fields"):
        validate_mapping(raw, known_selectors={"#name", "#email"})


def test_profile_field_missing_profile_field_name_is_rejected():
    raw = {
        "fields": [
            {"selector": "#name", "field_label": "a", "classification": "profile_field"},
        ]
    }
    with pytest.raises(ValueError):
        validate_mapping(raw, known_selectors={"#name"})


def test_profile_field_with_unknown_field_name_is_rejected():
    raw = {
        "fields": [
            {
                "selector": "#name",
                "field_label": "a",
                "classification": "profile_field",
                "profile_field": "favourite_colour",
            },
        ]
    }
    with pytest.raises(ValueError):
        validate_mapping(raw, known_selectors={"#name"})


def test_checkbox_missing_checkbox_action_is_rejected():
    raw = {
        "fields": [
            {"selector": "#terms", "field_label": "a", "classification": "checkbox"},
        ]
    }
    with pytest.raises(ValueError):
        validate_mapping(raw, known_selectors={"#terms"})
