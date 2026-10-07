"""
Operator tool: clear a stale FAILED EntryRecord so its channel becomes
eligible to be drafted again.

Why this exists (2026-10-07): eligibility.py's find_draftable_channels()
treats *any* existing EntryRecord for a (promotion, channel) pair as
"already attempted", so a FAILED record — however transient the cause (a
Gemini 503, a since-fixed selector bug) — blocks that channel forever.
Until now the only way to clear one was hand-editing the production JSON
blob (done three times during the first real Global Commercial login
attempts, see docs/build-log.md, 2026-10-06), because the storage layer had
no delete() at all.

**Only FAILED records can be reset, and by default only draft-stage ones.**
Deleting a record makes the channel look never-attempted, so anything that
records a real action having happened must not be deletable by accident:
  - DRAFTED/APPROVED/SUBMITTED/SKIPPED are refused outright. SUBMITTED means
    a real entry went out; APPROVED/DRAFTED are a human's live decision in
    flight; SKIPPED is usually a deliberate human "no" (the Telegram Skip
    tap).
  - A FAILED record that carries `approved_at` or `fill_plan` came from the
    *submit* stage (submit_one only ever runs on an APPROVED record with a
    saved plan; draft-stage failures never have either). That failure may
    have happened after the real click — e.g. the post-submit screenshot
    raising — meaning the form could genuinely have gone through. Resetting
    it would let the channel be drafted and entered a second time, so it's
    refused unless `--allow-submit-stage` is passed, after checking the
    competition site/confirmation email yourself. (Even then, the channel
    only becomes *re-draftable*: a fresh draft still needs a fresh human
    Approve tap before anything is submitted.)

Nothing here runs automatically; this is a deliberate, manual tool.

    python -m radiocomp.reset_failed_entry --list
    python -m radiocomp.reset_failed_entry <record_id> [<record_id> ...]
    python -m radiocomp.reset_failed_entry --promotion <promotion_id> [...]
    python -m radiocomp.reset_failed_entry --allow-submit-stage <record_id>

Reads/writes whatever STORAGE_BACKEND is configured, same as every other
tool here — point it at gcs (with GCP_PROJECT_ID/GCS_BUCKET_NAME) to act on
production.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from .models import EntryRecord, EntryStatus, Promotion
from .storage.base import Repository, get_repository


def _is_submit_stage(record: EntryRecord) -> bool:
    return record.approved_at is not None or record.fill_plan is not None


def reset_failed_record(
    entry_repo: Repository[EntryRecord], record_id: str, allow_submit_stage: bool = False
) -> EntryRecord:
    """Deletes one FAILED record and returns it. Raises ValueError (and
    deletes nothing) if the record doesn't exist, isn't FAILED, or is a
    submit-stage failure and `allow_submit_stage` wasn't passed — see module
    docstring for why each of these is refused."""
    record = entry_repo.get(record_id)
    if record is None:
        raise ValueError(f"no EntryRecord with id {record_id!r}")
    if record.status != EntryStatus.FAILED:
        raise ValueError(
            f"EntryRecord {record_id!r} has status {record.status.value!r} — only FAILED records can be reset "
            "(anything else records a real decision or action having happened)"
        )
    if _is_submit_stage(record) and not allow_submit_stage:
        raise ValueError(
            f"EntryRecord {record_id!r} failed at the submit stage (it was approved and had a saved fill plan) — "
            "the form may genuinely have been submitted before the failure, and resetting it could lead to a "
            "duplicate entry. Check the competition site/confirmation email first, then re-run with "
            "--allow-submit-stage if you're sure."
        )
    if not entry_repo.delete(record_id):
        raise ValueError(f"EntryRecord {record_id!r} disappeared before it could be deleted")
    return record


def failed_record_ids_for_promotion(entry_repo: Repository[EntryRecord], promotion_id: str) -> list[str]:
    return [
        r.id for r in entry_repo.list() if r.promotion_id == promotion_id and r.status == EntryStatus.FAILED
    ]


def _describe(record: EntryRecord, promo: Optional[Promotion]) -> str:
    title = promo.title if promo else "(promotion not found)"
    error = (record.submission_error or "").strip().splitlines()[0:1]
    stage = "submit-stage" if _is_submit_stage(record) else "draft-stage"
    return (
        f"record {record.id} | promotion {record.promotion_id} | {title!r} | {stage} | "
        f"{error[0][:160] if error else '(no error text)'}"
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Clear stale FAILED EntryRecords so their channels can be retried.")
    parser.add_argument("ids", nargs="*", help="EntryRecord ids (or promotion ids, with --promotion)")
    parser.add_argument("--list", action="store_true", help="list every FAILED record and exit")
    parser.add_argument("--promotion", action="store_true", help="treat ids as promotion ids: reset all their FAILED records")
    parser.add_argument(
        "--allow-submit-stage",
        action="store_true",
        help="also allow resetting a failure from the submit stage (the form may really have been submitted)",
    )
    args = parser.parse_args(argv)

    entry_repo = get_repository("entry_records", EntryRecord)
    promo_repo = get_repository("promotions", Promotion)
    promos = {p.id: p for p in promo_repo.list()}

    if args.list:
        failed = [r for r in entry_repo.list() if r.status == EntryStatus.FAILED]
        if not failed:
            print("No FAILED records.")
        for r in failed:
            print(_describe(r, promos.get(r.promotion_id)))
        return 0

    if not args.ids:
        parser.error("give at least one id, or use --list")

    record_ids: list[str] = []
    for given in args.ids:
        if args.promotion:
            found = failed_record_ids_for_promotion(entry_repo, given)
            if not found:
                print(f"REFUSED/none: no FAILED records for promotion {given!r}")
            record_ids.extend(found)
        else:
            record_ids.append(given)

    exit_code = 0 if record_ids or not args.promotion else 1
    for record_id in record_ids:
        try:
            record = reset_failed_record(entry_repo, record_id, allow_submit_stage=args.allow_submit_stage)
        except ValueError as exc:
            print(f"REFUSED: {exc}")
            exit_code = 1
            continue
        print(f"RESET: {_describe(record, promos.get(record.promotion_id))}")
        print(f"  deleted record (audit copy): {record.model_dump_json()}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
