"""
Stage 1 of the two-stage flow: navigate to a qualifying web_form entry
page, get an LLM field mapping, fill it in (never submit), screenshot it,
and ask for confirmation. See eligibility.py for what "qualifying" means
and why WEB_FORM is checked as its own hard condition.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from ..models import EntryChannel, EntryRecord, EntryStatus, Promotion
from ..storage.base import get_repository
from ..storage.user_profile_store import load_user_profile
from . import browser, llm_mapping, notify_draft, screenshots
from .fill_plan import build_fill_actions, needs_manual_input, validate_mapping

logger = logging.getLogger(__name__)


def draft_one(promo: Promotion, channel: EntryChannel) -> EntryRecord:
    entry_repo = get_repository("entry_records", EntryRecord)
    url = channel.channel_url_or_number or promo.source_url

    with browser.open_page(url) as page:
        fields = browser.extract_form_fields(page)

        if not fields:
            record = EntryRecord(
                promotion_id=promo.id,
                channel_type=channel.channel_type,
                channel_id=channel.id,
                status=EntryStatus.SKIPPED,
                submission_error="no form fields found on the entry page",
            )
            entry_repo.add(record)
            logger.warning("No form fields found for promotion %s, skipping draft", promo.id)
            return record

        raw = llm_mapping.request_field_mapping(fields)
        try:
            mapping = validate_mapping(raw, known_selectors={f["selector"] for f in fields})
        except ValueError as exc:
            record = EntryRecord(
                promotion_id=promo.id,
                channel_type=channel.channel_type,
                channel_id=channel.id,
                status=EntryStatus.SKIPPED,
                submission_error=f"field mapping failed validation: {exc}",
            )
            entry_repo.add(record)
            logger.warning("Field mapping validation failed for promotion %s: %s", promo.id, exc)
            return record

        if needs_manual_input(mapping):
            # The "worth your five minutes" case (spec section 6) — never
            # auto-filled, never silently skipped without telling you.
            record = EntryRecord(
                promotion_id=promo.id,
                channel_type=channel.channel_type,
                channel_id=channel.id,
                status=EntryStatus.SKIPPED,
                compliance_note="Needs your own input (creative/skill-based or unmappable field) — see source_url",
            )
            entry_repo.add(record)
            notify_draft.send_manual_input_flag(promo, channel, mapping)
            return record

        profile = load_user_profile()
        if profile is None:
            record = EntryRecord(
                promotion_id=promo.id,
                channel_type=channel.channel_type,
                channel_id=channel.id,
                status=EntryStatus.FAILED,
                submission_error="no UserProfile configured — run `python -m radiocomp.setup_user_profile`",
            )
            entry_repo.add(record)
            logger.error("No UserProfile configured, cannot draft promotion %s", promo.id)
            return record

        actions = build_fill_actions(mapping, profile)
        browser.apply_fill_actions(page, actions)

        record = EntryRecord(
            promotion_id=promo.id,
            channel_type=channel.channel_type,
            channel_id=channel.id,
            status=EntryStatus.DRAFTED,
            fill_plan=mapping.model_dump(mode="json"),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = str(Path(tmpdir) / f"{record.id}_draft.png")
            browser.screenshot(page, local_path)
            record.draft_screenshot_path = screenshots.save_screenshot(local_path, record.id, "draft")
            entry_repo.add(record)
            notify_draft.send_draft_confirmation(promo, channel, record, local_path)

        logger.info("Drafted promotion %s channel %s", promo.id, channel.id)
        return record
