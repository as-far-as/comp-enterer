"""
reset_failed_entry.py — the operator tool for clearing a stale FAILED
EntryRecord (see its docstring and docs/build-log.md, 2026-10-07).

The load-bearing behaviours: it only ever deletes FAILED records; it
refuses submit-stage failures (which may have gone through for real) unless
explicitly told otherwise; and — the actual point — resetting a draft-stage
failure really does make the channel eligible to be drafted again via the
real eligibility.find_draftable_channels(), not just remove a row.

Local storage in a tmp dir throughout; no network.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from radiocomp import config
from radiocomp.entry_execution.eligibility import find_draftable_channels
from radiocomp.models import (
    DiscoveredVia,
    EntryChannel,
    EntryChannelType,
    EntryRecord,
    EntryStatus,
    Promotion,
)
from radiocomp.reset_failed_entry import (
    failed_record_ids_for_promotion,
    main,
    reset_failed_record,
)
from radiocomp.storage.base import get_repository


def _use_local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)


def _seed(promo_title="Win a Thing"):
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    promo = Promotion(
        station_name_raw="Radio X",
        title=promo_title,
        discovered_via=DiscoveredVia.DIRECT,
        source_url="https://example.com/win",
        dedup_hash=f"hash-{promo_title}",
    )
    channel = EntryChannel(
        promotion_id=promo.id,
        channel_type=EntryChannelType.WEB_FORM,
        is_free_route=True,
        review_recommended=False,
        channel_url_or_number="https://example.com/win",
    )
    promo_repo.add(promo)
    channel_repo.add(channel)
    return promo, channel


def _add_record(promo, channel, status, **overrides) -> EntryRecord:
    record = EntryRecord(
        promotion_id=promo.id,
        channel_type=channel.channel_type,
        channel_id=channel.id,
        status=status,
        **overrides,
    )
    get_repository("entry_records", EntryRecord).add(record)
    return record


def _draftable(promo, channel) -> list:
    entries = list(get_repository("entry_records", EntryRecord).list())
    return find_draftable_channels([promo], [channel], entries)


# --- reset_failed_record ----------------------------------------------------


def test_resetting_a_draft_stage_failure_makes_the_channel_draftable_again(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed()
    record = _add_record(promo, channel, EntryStatus.FAILED, submission_error="LLM field-mapping request failed: 503")
    assert _draftable(promo, channel) == []  # the real bug: a stale FAILED record blocks it forever

    deleted = reset_failed_record(get_repository("entry_records", EntryRecord), record.id)

    assert deleted.id == record.id
    assert _draftable(promo, channel) == [(promo, channel)]


@pytest.mark.parametrize(
    "status", [EntryStatus.DRAFTED, EntryStatus.APPROVED, EntryStatus.SUBMITTED, EntryStatus.SKIPPED]
)
def test_refuses_anything_that_is_not_failed_and_leaves_it_in_place(monkeypatch, tmp_path, status):
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed()
    record = _add_record(promo, channel, status)
    repo = get_repository("entry_records", EntryRecord)

    with pytest.raises(ValueError, match="only FAILED records can be reset"):
        reset_failed_record(repo, record.id)

    assert repo.get(record.id) is not None


def test_refuses_a_submit_stage_failure_by_default_because_it_may_have_really_gone_through(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed()
    record = _add_record(
        promo,
        channel,
        EntryStatus.FAILED,
        approved_at=datetime(2026, 10, 7, 9, 0, 0),
        fill_plan={"fields": []},
        submission_error="unexpected error during submit: screenshot failed after the click",
    )
    repo = get_repository("entry_records", EntryRecord)

    with pytest.raises(ValueError, match="submit stage"):
        reset_failed_record(repo, record.id)

    assert repo.get(record.id) is not None  # still there — a duplicate real entry is the thing being prevented


def test_a_fill_plan_alone_is_enough_to_count_as_submit_stage(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed()
    record = _add_record(promo, channel, EntryStatus.FAILED, fill_plan={"fields": []})

    with pytest.raises(ValueError, match="submit stage"):
        reset_failed_record(get_repository("entry_records", EntryRecord), record.id)


def test_allow_submit_stage_overrides_that_guard(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed()
    record = _add_record(
        promo, channel, EntryStatus.FAILED, approved_at=datetime(2026, 10, 7, 9, 0, 0), fill_plan={"fields": []}
    )
    repo = get_repository("entry_records", EntryRecord)

    reset_failed_record(repo, record.id, allow_submit_stage=True)

    assert repo.get(record.id) is None


def test_unknown_record_id_raises(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="no EntryRecord"):
        reset_failed_record(get_repository("entry_records", EntryRecord), "nope")


def test_failed_record_ids_for_promotion_only_returns_failed_ones_for_that_promotion(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    promo_a, channel_a = _seed("A")
    promo_b, channel_b = _seed("B")
    failed_a = _add_record(promo_a, channel_a, EntryStatus.FAILED)
    _add_record(promo_a, channel_a, EntryStatus.SKIPPED)
    _add_record(promo_b, channel_b, EntryStatus.FAILED)

    ids = failed_record_ids_for_promotion(get_repository("entry_records", EntryRecord), promo_a.id)

    assert ids == [failed_a.id]


# --- CLI (main) --------------------------------------------------------------


def test_list_shows_failed_records_with_their_stage_and_error(monkeypatch, tmp_path, capsys):
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed("Nescafe Thing")
    record = _add_record(promo, channel, EntryStatus.FAILED, submission_error="Gemini 503 high demand")

    code = main(["--list"])

    out = capsys.readouterr().out
    assert code == 0
    assert record.id in out
    assert "Nescafe Thing" in out
    assert "draft-stage" in out
    assert "Gemini 503 high demand" in out


def test_list_with_nothing_failed_says_so(monkeypatch, tmp_path, capsys):
    _use_local_storage(monkeypatch, tmp_path)

    assert main(["--list"]) == 0

    assert "No FAILED records" in capsys.readouterr().out


def test_main_resets_a_record_prints_an_audit_copy_and_exits_zero(monkeypatch, tmp_path, capsys):
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed()
    record = _add_record(promo, channel, EntryStatus.FAILED, submission_error="boom")

    code = main([record.id])

    out = capsys.readouterr().out
    assert code == 0
    assert f"RESET: record {record.id}" in out
    assert "audit copy" in out and '"status":"failed"' in out
    assert get_repository("entry_records", EntryRecord).get(record.id) is None


def test_main_exits_nonzero_and_deletes_nothing_when_refused(monkeypatch, tmp_path, capsys):
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed()
    record = _add_record(promo, channel, EntryStatus.SUBMITTED)

    code = main([record.id])

    assert code == 1
    assert "REFUSED" in capsys.readouterr().out
    assert get_repository("entry_records", EntryRecord).get(record.id) is not None


def test_main_promotion_mode_resets_every_failed_record_for_that_promotion(monkeypatch, tmp_path, capsys):
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed()
    first = _add_record(promo, channel, EntryStatus.FAILED)
    second = _add_record(promo, channel, EntryStatus.FAILED)
    skipped = _add_record(promo, channel, EntryStatus.SKIPPED)

    code = main(["--promotion", promo.id])

    repo = get_repository("entry_records", EntryRecord)
    assert code == 0
    assert repo.get(first.id) is None and repo.get(second.id) is None
    assert repo.get(skipped.id) is not None  # a deliberate human skip is never touched


def test_main_promotion_mode_with_no_failed_records_exits_nonzero(monkeypatch, tmp_path, capsys):
    _use_local_storage(monkeypatch, tmp_path)
    promo, _channel = _seed()

    code = main(["--promotion", promo.id])

    assert code == 1
    assert "no FAILED records" in capsys.readouterr().out


def test_main_with_no_ids_and_no_list_is_a_usage_error(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)

    with pytest.raises(SystemExit):
        main([])
