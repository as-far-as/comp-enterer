"""
The schema an LLM-produced field mapping must satisfy before any code
touches a real page — same "never trust the model's output as-is" posture
as every adapter's classifier in this codebase, just applied to an LLM
response instead of scraped HTML. validate_mapping() is the actual safety
boundary: llm_mapping.py's raw response is untrusted input right up until
it passes every check here.

Nothing in this file ever sees a real UserProfile value — build_fill_actions()
is where PII actually enters the picture, deliberately kept separate from
llm_mapping.py's Claude call so the LLM step itself never handles it.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, model_validator

from ..models import UserProfile

PROFILE_FIELDS = frozenset({"name", "date_of_birth", "address", "phone", "email"})


class FieldClassification(str, Enum):
    PROFILE_FIELD = "profile_field"
    CHECKBOX = "checkbox"
    CREATIVE_FREETEXT = "creative_freetext"  # a tie-breaker, "in 25 words or fewer" — never auto-filled,
    # see the module docstring on entry_execution/llm_mapping.py for why
    UNMAPPABLE = "unmappable"  # anything else — never guessed


class CheckboxAction(str, Enum):
    CHECK = "check"
    LEAVE_UNCHECKED = "leave_unchecked"


class MappedField(BaseModel):
    selector: str
    field_label: str
    classification: FieldClassification
    profile_field: Optional[str] = None
    checkbox_action: Optional[CheckboxAction] = None

    @model_validator(mode="after")
    def _companion_fields_present(self) -> "MappedField":
        if self.classification == FieldClassification.PROFILE_FIELD:
            if self.profile_field not in PROFILE_FIELDS:
                raise ValueError(f"profile_field must be one of {sorted(PROFILE_FIELDS)}, got {self.profile_field!r}")
        if self.classification == FieldClassification.CHECKBOX and self.checkbox_action is None:
            raise ValueError(f"checkbox field {self.selector!r} is missing checkbox_action")
        return self


class FormMapping(BaseModel):
    fields: list[MappedField]
    notes: str = ""


def validate_mapping(raw: dict, known_selectors: set[str]) -> FormMapping:
    """Raises ValueError on anything untrustworthy — callers must treat
    that exactly like a failed fetch elsewhere in this codebase: log, flag
    for review, never touch the real page. Checks, in order:
      - it's structurally a FormMapping at all (field-level checks above)
      - every returned selector was one we actually sent (blocks an
        invented selector)
      - no duplicate selectors (blocks silently mapping two fields to one)
      - the field count matches what we sent (blocks silently dropping a
        field the form actually has)
    """
    mapping = FormMapping.model_validate(raw)

    seen: set[str] = set()
    for field in mapping.fields:
        if field.selector not in known_selectors:
            raise ValueError(f"selector {field.selector!r} was not among the fields we sent")
        if field.selector in seen:
            raise ValueError(f"duplicate selector {field.selector!r}")
        seen.add(field.selector)

    if len(mapping.fields) != len(known_selectors):
        raise ValueError(f"expected {len(known_selectors)} fields, got {len(mapping.fields)}")

    return mapping


def needs_manual_input(mapping: FormMapping) -> bool:
    """True if any field requires a human's own input — a creative/
    skill-based question, or anything the model couldn't confidently
    classify. The whole draft is refused in that case (see draft.py),
    never partially auto-filled around the field it can't handle."""
    return any(
        f.classification in (FieldClassification.CREATIVE_FREETEXT, FieldClassification.UNMAPPABLE)
        for f in mapping.fields
    )


def build_fill_actions(mapping: FormMapping, profile: UserProfile) -> list[dict]:
    """Where PII actually enters the picture — never inside the LLM call.
    Call only after confirming `not needs_manual_input(mapping)`."""
    values = {
        "name": profile.name,
        "date_of_birth": profile.date_of_birth.isoformat(),
        "address": profile.address,
        "phone": profile.phone,
        "email": profile.email,
    }
    actions: list[dict] = []
    for field in mapping.fields:
        if field.classification == FieldClassification.PROFILE_FIELD:
            actions.append({"type": "fill", "selector": field.selector, "value": values[field.profile_field]})
        elif field.classification == FieldClassification.CHECKBOX:
            action_type = "check" if field.checkbox_action == CheckboxAction.CHECK else "leave_unchecked"
            actions.append({"type": action_type, "selector": field.selector})
        # CREATIVE_FREETEXT / UNMAPPABLE never produce an action — the
        # caller must have already refused to proceed via needs_manual_input().
    return actions
