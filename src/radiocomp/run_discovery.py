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

Deliberately just discovery, nothing more: it fetches and stores
Promotions/EntryChannels, same as running each adapter by hand. It doesn't
run the compliance engine (spec section 4) or draft/submit anything — there's
no entry-execution engine yet (spec section 5, not built) and no persisted
place to put a compliance result even if there were. Run
`python -m radiocomp.compliance.engine` — or just import and call
check_promotion() — separately when you actually want that, against
whatever's been discovered.

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

    for label, ingest in adapters:
        try:
            outcome = ingest()
            # talksport/radioexe return (promotions, channels); the
            # aggregators return just promotions — count promotions either way.
            new_count = len(outcome[0]) if isinstance(outcome, tuple) else len(outcome)
            results[label] = new_count
            logger.info("%s: %d new promotion(s)", label, new_count)
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

    return 1 if len(failures) == len(adapters) else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())
