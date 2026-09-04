"""
Single entrypoint for a scheduled discovery pass — what the Cloud Run Job
actually runs. Ties together every ingest()-shaped adapter that *can* run
from Cloud Run (one aggregator, two direct-station monitors) into one
process with one exit code, so Cloud Scheduler has one thing to trigger
rather than three.

loquax isn't included here — Loquax bans Google Cloud's shared egress IP
range outright (confirmed live, 2026-09-03: "Your IP address has been
banned."), so it would fail on every single run from this Job. It runs
instead from a separate scheduled GitHub Actions workflow
(.github/workflows/loquax-scheduled.yml), whose runners aren't banned,
writing into the same GCS bucket via Workload Identity Federation. See
docs/build-log.md for the full investigation.

Fetches and stores Promotions/EntryChannels, same as running each adapter
by hand, then sends a Telegram notification for anything new
(notify.send.notify_new_promotions — see that module for the compliance
check and Approve/Skip button logic). Still doesn't draft or submit
anything itself — there's no entry-execution engine yet (spec section 5,
not built); Approve/Skip only ever records an EntryRecord, it never fills
in or submits a real form.

Station seeding (stations/seed_local_independent.py) also isn't run here —
that's a one-off/occasional maintenance task, not something that needs
repeating every scheduled pass.

Every adapter's errors are caught and logged rather than allowed to take
the whole run down — one station's page changing shape shouldn't block the
others from still running. The process exits non-zero only if every single
adapter failed, which is what actually warrants Cloud Scheduler treating
the run as failed.
"""

from __future__ import annotations

import logging
import sys

from .models import Promotion
from .notify.send import notify_new_promotions

logger = logging.getLogger(__name__)


def _load_adapters() -> list[tuple[str, object]]:
    """(label, ingest callable) pairs — add new adapters here as they're
    built (except loquax — see module docstring). A fresh list per call,
    not a module-level global appended to, so calling this more than once
    (e.g. from a test) can't duplicate entries."""
    from .aggregators import theprizefinder
    from .stations import radioexe, talksport

    return [
        ("theprizefinder", theprizefinder.ingest),
        ("talksport", talksport.ingest),
        ("radioexe", radioexe.ingest),
    ]


def main() -> int:
    adapters = _load_adapters()
    results: dict[str, int] = {}
    failures: list[str] = []
    all_new_promotions: list[Promotion] = []

    for label, ingest in adapters:
        try:
            outcome = ingest()
            # talksport/radioexe return (promotions, channels); the
            # aggregators return just promotions — either way, get the list.
            new_promotions = outcome[0] if isinstance(outcome, tuple) else outcome
            all_new_promotions.extend(new_promotions)
            results[label] = len(new_promotions)
            logger.info("%s: %d new promotion(s)", label, len(new_promotions))
        except Exception:
            failures.append(label)
            logger.exception("%s: ingest failed", label)

    total_new = sum(results.values())
    logger.info(
        "Discovery pass complete: %d adapter(s) ran, %d failed, %d new promotion(s) total",
        len(adapters) - len(failures),
        len(failures),
        total_new,
    )

    try:
        notify_new_promotions(all_new_promotions)
    except Exception:
        # A Telegram outage isn't a discovery failure — never let this
        # flip the exit code the scheduler watches.
        logger.exception("Notification step failed")

    return 1 if len(failures) == len(adapters) else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # httpx logs full request URLs at INFO, and Telegram's Bot API puts
    # the bot token directly in the URL path — this would otherwise leak
    # the token into Cloud Logging on every notify call (confirmed live,
    # 2026-09-04). See notify/telegram_client.py.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sys.exit(main())
