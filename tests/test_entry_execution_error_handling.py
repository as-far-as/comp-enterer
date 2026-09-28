"""
The backstop added to draft.py/submit.py after a real incident
(2026-09-28, see both modules' own docstrings): an uncaught exception
anywhere in the draft/submit flow used to propagate straight out with no
EntryRecord ever saved, so the same channel looked "never attempted"
again on the very next run — and, combined with Cloud Run's own
retry-on-timeout behaviour, one transient failure (a real Gemini
free-tier rate-limit hit) turned into several repeated real Global
Player sign-ins in a row. These tests prove *any* unexpected exception —
not just the specific one seen live — now results in a saved FAILED
record instead of silently propagating.

Both openers are faked as no-op context managers (or ones that raise),
same technique as test_entry_execution_routing.py — this file is about
what gets *saved* when something goes wrong, not live Playwright
mechanics.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from radiocomp import config
from radiocomp.entry_execution import browser, draft, llm_mapping, submit
from radiocomp.models import (
    DiscoveredVia,
    EntryChannel,
    EntryChannelType,
    EntryRecord,
    EntryStatus,
    Promotion,
    UserProfile,
)
from radiocomp.storage.base import get_repository
from radiocomp.storage.user_profile_store import save_user_profile


def _use_local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)


def _seed_promotion_and_channel():
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    promo = Promotion(
        station_name_raw="Radio X",
        title="Win a Thing",
        discovered_via=DiscoveredVia.DIRECT,
        source_url="https://example.com/radiox-comp",
        dedup_hash="hash-error-handling",
    )
    channel = EntryChannel(
        promotion_id=promo.id,
        channel_type=EntryChannelType.WEB_FORM,
        is_free_route=True,
        review_recommended=False,
        channel_url_or_number="https://example.com/radiox-comp",
    )
    promo_repo.add(promo)
    channel_repo.add(channel)
    return promo, channel


def _seed_user_profile():
    save_user_profile(
        UserProfile(
            name="Adan Farpon",
            date_of_birth=date(1990, 1, 1),
            address="1 Example Street, London, EX4 4PL",
            phone="07000000000",
            email="adan@example.com",
        )
    )


@contextmanager
def _open_page_yielding_a_page_with_one_field(url):
    yield object()


def test_draft_one_saves_failed_record_when_llm_mapping_raises(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed_promotion_and_channel()
    monkeypatch.setattr(browser, "open_page", _open_page_yielding_a_page_with_one_field)
    monkeypatch.setattr(browser, "extract_form_fields", lambda page: [{"selector": "#x", "label": "Name"}])
    monkeypatch.setattr(
        llm_mapping,
        "request_field_mapping",
        lambda fields: (_ for _ in ()).throw(RuntimeError("simulated Gemini free-tier rate limit")),
    )

    record = draft.draft_one(promo, channel)

    assert record.status == EntryStatus.FAILED
    assert "LLM field-mapping request failed" in record.submission_error
    assert "simulated Gemini free-tier rate limit" in record.submission_error
    saved = get_repository("entry_records", EntryRecord).get(record.id)
    assert saved is not None and saved.status == EntryStatus.FAILED


def test_draft_one_saves_failed_record_for_any_other_unhandled_exception(monkeypatch, tmp_path):
    # Not the LLM call specifically — e.g. the opener itself (sign-in,
    # navigation) raising, which is exactly what was NOT caught before
    # this fix.
    _use_local_storage(monkeypatch, tmp_path)
    promo, channel = _seed_promotion_and_channel()

    @contextmanager
    def _raising_opener(url):
        raise RuntimeError("simulated sign-in/navigation failure")
        yield  # pragma: no cover — unreachable, makes this a generator function

    monkeypatch.setattr(browser, "open_page", _raising_opener)

    record = draft.draft_one(promo, channel)

    assert record.status == EntryStatus.FAILED
    assert "unexpected error during draft" in record.submission_error
    assert "simulated sign-in/navigation failure" in record.submission_error
    saved = get_repository("entry_records", EntryRecord).get(record.id)
    assert saved is not None and saved.status == EntryStatus.FAILED


def test_submit_one_saves_failed_record_for_any_unhandled_exception(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    _seed_user_profile()
    promo, channel = _seed_promotion_and_channel()

    entry_repo = get_repository("entry_records", EntryRecord)
    record = EntryRecord(
        promotion_id=promo.id,
        channel_type=channel.channel_type,
        channel_id=channel.id,
        status=EntryStatus.APPROVED,
        fill_plan={"fields": [], "notes": "test"},
    )
    entry_repo.add(record)

    @contextmanager
    def _raising_opener(url):
        raise RuntimeError("simulated sign-in/navigation failure")
        yield  # pragma: no cover — unreachable, makes this a generator function

    monkeypatch.setattr(browser, "open_page", _raising_opener)

    result = submit.submit_one(record)

    assert result.status == EntryStatus.FAILED
    assert "unexpected error during submit" in result.submission_error
    assert "simulated sign-in/navigation failure" in result.submission_error
    saved = entry_repo.get(record.id)
    assert saved is not None and saved.status == EntryStatus.FAILED
