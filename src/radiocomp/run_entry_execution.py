"""
Single entrypoint for a scheduled entry-execution pass — what the
radio-comp-entry-execution Cloud Run Job actually runs, on its own
15-minute Cloud Scheduler cadence, separate from run_discovery.py's
hourly pass.

Checks eligibility first (eligibility.py — pure, no Playwright import) so
a tick with nothing to do exits before a browser is ever launched: most
ticks will find nothing, since discovery has so far never produced a
qualifying free web_form channel (see entry_execution/eligibility.py's
docstring / docs/build-log.md, 2026-09-04).

Three steps, each independently caught so one failing stage doesn't block
the others: draft anything newly eligible, submit anything approved since
the last tick, then check for any outcome reminders due. The process
exits non-zero only if a step raised outside its own per-item handling —
draft_one()/submit_one() already catch per-item failures onto the
EntryRecord itself (status=FAILED), not up to here.
"""

from __future__ import annotations

import logging
import sys

from .entry_execution.eligibility import find_draftable_channels, find_submittable_entries
from .models import EntryChannel, EntryRecord, Promotion

logger = logging.getLogger(__name__)


def main() -> int:
    from .storage.base import get_repository

    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    entry_repo = get_repository("entry_records", EntryRecord)

    promotions = list(promo_repo.list())
    channels = list(channel_repo.list())
    entries = list(entry_repo.list())

    draftable = find_draftable_channels(promotions, channels, entries)
    submittable = find_submittable_entries(entries)

    if not draftable and not submittable:
        logger.info("Nothing draftable or submittable this tick")
    else:
        from .entry_execution import draft, submit

        for promo, channel in draftable:
            try:
                draft.draft_one(promo, channel)
            except Exception:
                logger.exception("draft_one failed for promotion %s channel %s", promo.id, channel.id)

        for record in submittable:
            try:
                submit.submit_one(record)
            except Exception:
                logger.exception("submit_one failed for entry %s", record.id)

    try:
        from .outcomes.reminder import notify_pending_outcomes

        sent = notify_pending_outcomes()
        if sent:
            logger.info("Sent %d outcome reminder(s)", sent)
    except Exception:
        logger.exception("Outcome reminder step failed")

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # same token-in-URL leak risk as run_discovery.py
    sys.exit(main())
