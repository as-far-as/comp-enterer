"""
The one LLM call this feature makes: classify a competition entry form's
fields and map them to UserProfile data, generically, without any
per-site hardcoded selectors.

The model never sees any PII — only field structure (selector, label,
input type, options) and the five known UserProfile field *names*.
Literal values are substituted afterward, entirely in our own code
(fill_plan.build_fill_actions) — the same "credentials shouldn't pass
through an AI agent" caution this project already applies to the Telegram
bot token and the UserProfile setup script, applied here to keeping this
specific LLM call from ever handling the user's actual name/DOB/address/
phone.

Uses the Gemini API (client.interactions.create with a JSON response_format
carrying FormMapping's own JSON schema) rather than the Anthropic API this
was originally built against — switched 2026-09-08 at the user's explicit
request, to avoid tying this to their work Anthropic account; Gemini's
free tier (a personal Google account, no billing) is a better fit for how
rarely this actually runs. FormMapping.model_validate_json() on the
response still rejects a structurally-wrong response (including
FormMapping's own model_validator) before it reaches
fill_plan.validate_mapping()'s second, semantic layer of checks (selector
must be one we actually sent, no duplicates, field count matches) — a
response failing either layer is never trusted, same "never trust the
model's output as-is" posture as every adapter's classifier.

Model: gemini-3.8-flash — a mid-tier model, not the cheapest. A wrong
classification here has real consequences (an opted-in marketing checkbox,
a creative field silently auto-filled instead of flagged), and this runs
rarely enough (only when a promotion actually has a qualifying free
web-form channel — zero so far, see docs/build-log.md) that cost isn't
the consideration correctness is.
"""

from __future__ import annotations

from google import genai

from .fill_plan import FormMapping

_MODEL = "gemini-3.8-flash"

_SYSTEM_PROMPT = """You are analysing the structure of a UK radio-competition
entry form. You are given a list of form fields (selector, label, input
type, and any visible option text) extracted from a real page. You are
NEVER given or asked to invent any actual personal data — only classify
and map field *purpose*.

For every field in the input, produce exactly one mapping. Choose one
classification:

- "profile_field": the field clearly maps to one of these five known
  fields: name, date_of_birth, address, phone, email. Set profile_field
  to the matching name exactly.
- "checkbox": also set checkbox_action —
    "check" only for something required to submit and clearly about
      consenting to the competition's own rules, confirming age or
      eligibility, or accepting official terms and conditions.
    "leave_unchecked" for ANYTHING else, including any marketing,
      newsletter, partner-offer, or "keep me updated" opt-in, and for
      anything ambiguous. When in doubt, leave unchecked.
- "creative_freetext": any open-ended text asking for a creative,
  persuasive, or skill-based answer — a tie-breaker, "in 25 words or
  fewer...", "tell us why you deserve to win", a caption, a joke —
  anything beyond simple factual profile data.
- "unmappable": anything else you can't confidently classify — a field
  asking for information not in the five profile fields (favourite radio
  station, a referral code, a postcode-only lookup with no matching
  profile field), or anything you're unsure about. Never guess a mapping
  you aren't confident in — "unmappable" is always the safe default over
  a wrong guess.

Every selector in your response must be copied verbatim from the input —
never invent one, never alter one. Produce exactly one mapped field per
input field — never add or drop any."""


def request_field_mapping(form_fields: list[dict]) -> dict:
    """form_fields: [{"selector": ..., "label": ..., "input_type": ...,
    "options": [...]}]. No PII in this payload, ever.

    Returns the raw mapping dict (already Pydantic-validated against
    FormMapping's own schema and model_validator) — still untrusted with
    respect to *this specific form*, though: the caller must still run it
    through fill_plan.validate_mapping(raw, known_selectors) before acting
    on it, since only that call knows which selectors were actually sent.
    """
    client = genai.Client()  # reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the environment

    user_content = "Form fields:\n" + "\n".join(
        f"- selector={f['selector']!r} label={f['label']!r} type={f['input_type']!r}"
        + (f" options={f['options']!r}" if f.get("options") else "")
        for f in form_fields
    )

    interaction = client.interactions.create(
        model=_MODEL,
        input=user_content,
        system_instruction=_SYSTEM_PROMPT,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": FormMapping.model_json_schema(),
        },
    )

    mapping = FormMapping.model_validate_json(interaction.output_text)
    return mapping.model_dump(mode="json")
