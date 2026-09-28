"""
Stage 2 of the two-stage flow: re-navigate to the entry page and replay
the saved fill plan — no second LLM call, deterministic replay only, so a
stray page change between draft and confirm can't cause an unreviewed
action.

Concrete safety mechanism, not just a claim: extract_form_fields() tags
fields with a data-rc-field marker in deterministic DOM order on whatever
page it's called against (confirmed in
tests/test_entry_execution_form_extraction.py — the same markers get
reassigned to the same logical fields on a completely fresh page load, as
long as the form's structure hasn't changed). So submit.py calls
extract_form_fields() again on its own freshly-navigated page — re-tagging
it — before ever touching anything, then checks every selector the saved
plan needs is present on THAT freshly re-tagged page. A form that's
changed shape since the draft (fields added/removed/reordered) fails this
check and the whole submission is refused, not attempted.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime
from pathlib import Path

from .. import config
from ..models import EntryChannel, EntryRecord, EntryStatus, Promotion
from ..stations import global_win
from ..storage.base import get_repository
from ..storage.user_profile_store import load_user_profile
from . import browser, global_win_auth, notify_draft, screenshots
from .fill_plan import FormMapping, build_fill_actions

logger = logging.getLogger(__name__)


def submit_one(record: EntryRecord) -> EntryRecord:
    entry_repo = get_repository("entry_records", EntryRecord)
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)

    if record.fill_plan is None:
        # Defensive third layer, on top of eligibility.py's two hard
        # filters — an APPROVED WEB_FORM record should never lack a saved
        # plan, but refuse rather than ever attempting a blind submit.
        record.status = EntryStatus.FAILED
        record.submission_error = "no fill plan present — refusing a blind submit"
        entry_repo.upsert(record)
        logger.error("EntryRecord %s has no fill_plan, refusing to submit", record.id)
        return record

    promo = promo_repo.get(record.promotion_id)
    channel = channel_repo.get(record.channel_id) if record.channel_id else None
    if promo is None or channel is None:
        record.status = EntryStatus.FAILED
        record.submission_error = "promotion or channel no longer exists"
        entry_repo.upsert(record)
        return record

    is_global_win = promo.station_name_raw == global_win.STATION_NAME
    if is_global_win and not (config.GLOBAL_PLAYER_EMAIL and config.GLOBAL_PLAYER_PASSWORD):
        # Same hard-stop as draft.py's own routing branch — see there for
        # why. A draft can only have reached APPROVED (and so be
        # submittable at all) if drafting itself already succeeded with
        # real credentials configured, but this is checked again here
        # independently rather than assumed, since submit.py always
        # re-navigates fresh (see module docstring) and never trusts state
        # left over from the draft pass.
        record.status = EntryStatus.FAILED
        record.submission_error = "GLOBAL_PLAYER_EMAIL/PASSWORD not set"
        entry_repo.upsert(record)
        logger.error(
            "EntryRecord %s is a Global WIN channel but GLOBAL_PLAYER_EMAIL/PASSWORD are unset, refusing to submit",
            record.id,
        )
        notify_draft.send_submission_result(promo, record)
        return record

    profile = load_user_profile()
    if profile is None:
        record.status = EntryStatus.FAILED
        record.submission_error = "no UserProfile configured — run `python -m radiocomp.setup_user_profile`"
        entry_repo.upsert(record)
        return record

    opener = global_win_auth.open_authenticated_page if is_global_win else browser.open_page

    try:
        return _submit_one_inner(record, promo, channel, profile, opener, entry_repo)
    except Exception as exc:
        # Outer backstop, deliberately broad — mirrors draft.py's own (see
        # its docstring comment for the full incident this responds to,
        # 2026-09-28). Anything unhandled here (opener(url)'s own
        # sign-in/navigation failing, an unexpected exception mid-fill,
        # etc.) used to propagate straight out of submit_one() uncaught —
        # no EntryRecord update ever saved, so the same record looked
        # "still APPROVED, not yet submitted" again on the very next run,
        # and Cloud Run's own retry-on-timeout behaviour could turn one
        # transient failure into several repeated real sign-ins in a row.
        # Recording FAILED here for anything unhandled stops that.
        record.status = EntryStatus.FAILED
        record.submission_error = f"unexpected error during submit: {exc}"
        entry_repo.upsert(record)
        logger.exception("Unexpected error submitting record %s", record.id)
        notify_draft.send_submission_result(promo, record)
        return record


def _submit_one_inner(record: EntryRecord, promo: Promotion, channel: EntryChannel, profile, opener, entry_repo):
    mapping = FormMapping.model_validate(record.fill_plan)
    actions = build_fill_actions(mapping, profile)
    url = channel.channel_url_or_number or promo.source_url

    with opener(url) as page:
        # Re-tag the freshly-navigated page — see module docstring for why
        # this, not a raw check against an untagged page, is the actual
        # safety mechanism.
        browser.extract_form_fields(page)

        missing = [a["selector"] for a in actions if page.locator(a["selector"]).count() == 0]
        if missing:
            record.status = EntryStatus.FAILED
            record.submission_error = f"page structure changed since draft — selector(s) not found: {missing}"
            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = str(Path(tmpdir) / f"{record.id}_submit_failed.png")
                browser.screenshot(page, local_path)
                record.submitted_screenshot_path = screenshots.save_screenshot(local_path, record.id, "submit_failed")
            entry_repo.upsert(record)
            logger.error("Submit refused for %s: %s", record.id, record.submission_error)
            notify_draft.send_submission_result(promo, record)
            return record

        browser.apply_fill_actions(page, actions)
        try:
            browser.click_submit(page)
        except RuntimeError as exc:
            record.status = EntryStatus.FAILED
            record.submission_error = str(exc)
            entry_repo.upsert(record)
            notify_draft.send_submission_result(promo, record)
            return record

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = str(Path(tmpdir) / f"{record.id}_submitted.png")
            browser.screenshot(page, local_path)
            record.submitted_screenshot_path = screenshots.save_screenshot(local_path, record.id, "submitted")

        record.status = EntryStatus.SUBMITTED
        record.submitted_at = datetime.utcnow()
        entry_repo.upsert(record)
        logger.info("Submitted promotion %s channel %s", record.promotion_id, record.channel_id)
        notify_draft.send_submission_result(promo, record)
        return record
