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

from .. import config
from ..models import EntryChannel, EntryRecord, EntryStatus, Promotion
from ..stations import global_win
from ..storage.base import get_repository
from ..storage.user_profile_store import load_user_profile
from . import browser, global_win_auth, llm_mapping, notify_draft, screenshots
from .fill_plan import build_fill_actions, needs_manual_input, validate_mapping

logger = logging.getLogger(__name__)


def draft_one(promo: Promotion, channel: EntryChannel) -> EntryRecord:
    entry_repo = get_repository("entry_records", EntryRecord)
    url = channel.channel_url_or_number or promo.source_url

    is_global_win = promo.station_name_raw == global_win.STATION_NAME
    if is_global_win and not (config.GLOBAL_PLAYER_EMAIL and config.GLOBAL_PLAYER_PASSWORD):
        # Same shape as the "no UserProfile configured" hard-stop below —
        # fail clearly rather than attempting anything. Global WIN's own
        # entry form requires a real signed-in session (see
        # global_win_auth.py's docstring); with no credentials configured
        # there is nothing this engine can do for this channel at all.
        record = EntryRecord(
            promotion_id=promo.id,
            channel_type=channel.channel_type,
            channel_id=channel.id,
            status=EntryStatus.FAILED,
            submission_error="GLOBAL_PLAYER_EMAIL/PASSWORD not set",
        )
        entry_repo.add(record)
        logger.error(
            "Promotion %s is a Global WIN channel but GLOBAL_PLAYER_EMAIL/PASSWORD are unset, refusing to draft",
            promo.id,
        )
        return record

    opener = global_win_auth.open_authenticated_page if is_global_win else browser.open_page

    try:
        return _draft_one_inner(promo, channel, url, opener, entry_repo)
    except Exception as exc:
        # Outer backstop, deliberately broad — a real gap found live
        # (2026-09-28): an uncaught exception anywhere in this function
        # (originally just the LLM field-mapping call, but the same is
        # true of opener(url)'s own sign-in/navigation, or anything else
        # not already given its own specific handler below) used to
        # propagate straight out of draft_one() — run_entry_execution.py's
        # own per-item try/except would log it and move on, but no
        # EntryRecord ever got saved, so the channel looked "never
        # attempted" again on the very next run. Combined with Cloud
        # Run's own retry-on-timeout behaviour, one transient failure (a
        # real Gemini free-tier rate-limit hit, in practice) turned into
        # several repeated real sign-ins in a row for a Global WIN
        # channel — exactly the kind of repeated-login pattern this
        # project has tried hard to avoid. Recording FAILED here, for
        # *anything* unhandled, stops a channel from being silently
        # retried on every single run regardless of what actually broke.
        record = EntryRecord(
            promotion_id=promo.id,
            channel_type=channel.channel_type,
            channel_id=channel.id,
            status=EntryStatus.FAILED,
            submission_error=f"unexpected error during draft: {exc}",
        )
        entry_repo.add(record)
        logger.exception("Unexpected error drafting promotion %s", promo.id)
        return record


def _draft_one_inner(promo: Promotion, channel: EntryChannel, url: str, opener, entry_repo) -> EntryRecord:
    with opener(url) as page:
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

        try:
            raw = llm_mapping.request_field_mapping(fields)
        except Exception as exc:
            # A more specific message than the outer backstop's generic
            # one, for the failure mode actually seen live (Gemini
            # free-tier rate limiting) — see draft_one()'s own docstring
            # comment for the full story.
            record = EntryRecord(
                promotion_id=promo.id,
                channel_type=channel.channel_type,
                channel_id=channel.id,
                status=EntryStatus.FAILED,
                submission_error=f"LLM field-mapping request failed: {exc}",
            )
            entry_repo.add(record)
            logger.error("LLM field-mapping request failed for promotion %s: %s", promo.id, exc)
            return record

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
