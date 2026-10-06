"""
Routing tests for draft.py/submit.py's per-source opener branches (see
entry_execution/global_win_auth.py's and global_commercial_auth.py's own
docstrings, and docs/build-log.md, 2026-09-28/2026-10-06): a Global WIN
promotion must go through global_win_auth.open_authenticated_page(), a
Global Commercial promotion through
global_commercial_auth.open_authenticated_page(), everything else through
the existing browser.open_page() — and either authenticated source with
no real credentials configured must fail closed (EntryStatus.FAILED)
*before* ever opening a browser at all.

Both openers are faked here as no-op context managers yielding a plain
sentinel object — this file is about which one gets called with which
URL, not the live Playwright mechanics themselves (those were verified
live instead — see each auth companion's own docstring).
browser.extract_form_fields()/click_submit() are stubbed too, so no real
DOM/page object is ever needed and no live network call happens anywhere
in this file.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from radiocomp import config
from radiocomp.entry_execution import browser, draft, global_commercial_auth, global_win_auth, submit
from radiocomp.models import (
    DiscoveredVia,
    EntryChannel,
    EntryChannelType,
    EntryRecord,
    EntryStatus,
    Promotion,
    UserProfile,
)
from radiocomp.stations import global_commercial, global_win
from radiocomp.storage.base import get_repository
from radiocomp.storage.user_profile_store import save_user_profile


def _use_local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)


def _fake_openers(monkeypatch):
    """Records (which opener, url) for every call; both yield a plain
    sentinel rather than a real Playwright page — nothing downstream in
    these tests ever calls a method on it."""
    calls: list[tuple[str, str]] = []

    @contextmanager
    def fake_open_page(url):
        calls.append(("anonymous", url))
        yield object()

    @contextmanager
    def fake_open_authenticated_page(url):
        calls.append(("authenticated", url))
        yield object()

    @contextmanager
    def fake_open_commercial_page(url):
        calls.append(("commercial", url))
        yield object()

    monkeypatch.setattr(browser, "open_page", fake_open_page)
    monkeypatch.setattr(global_win_auth, "open_authenticated_page", fake_open_authenticated_page)
    monkeypatch.setattr(global_commercial_auth, "open_authenticated_page", fake_open_commercial_page)
    return calls


def _seed_promotion_and_channel(station_name_raw: str, url: str):
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)

    promo = Promotion(
        station_name_raw=station_name_raw,
        title="Win a Thing",
        discovered_via=DiscoveredVia.DIRECT,
        source_url=url,
        dedup_hash=f"hash-{station_name_raw}-{url}",
    )
    channel = EntryChannel(
        promotion_id=promo.id,
        channel_type=EntryChannelType.WEB_FORM,
        is_free_route=True,
        review_recommended=False,
        channel_url_or_number=url,
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


def _seed_submittable_entry_record(promo, channel):
    entry_repo = get_repository("entry_records", EntryRecord)
    record = EntryRecord(
        promotion_id=promo.id,
        channel_type=channel.channel_type,
        channel_id=channel.id,
        status=EntryStatus.APPROVED,
        fill_plan={"fields": [], "notes": "test — no real fields, just proving routing"},
    )
    entry_repo.add(record)
    return record


def _raise_no_submit_control(page):
    raise RuntimeError("stub: no submit control")


# --- draft.py -------------------------------------------------------------


def test_draft_one_uses_anonymous_opener_for_a_non_global_win_promotion(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    calls = _fake_openers(monkeypatch)
    monkeypatch.setattr(browser, "extract_form_fields", lambda page: [])
    promo, channel = _seed_promotion_and_channel("Radio X", "https://example.com/radiox-comp")

    record = draft.draft_one(promo, channel)

    assert calls == [("anonymous", "https://example.com/radiox-comp")]
    assert record.status == EntryStatus.SKIPPED


def test_draft_one_uses_authenticated_opener_for_a_global_win_promotion(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "GLOBAL_PLAYER_EMAIL", "test@example.com")
    monkeypatch.setattr(config, "GLOBAL_PLAYER_PASSWORD", "hunter2")
    calls = _fake_openers(monkeypatch)
    monkeypatch.setattr(browser, "extract_form_fields", lambda page: [])
    promo, channel = _seed_promotion_and_channel(
        global_win.STATION_NAME, "https://winplus.heart.co.uk/competition/1/win-a-thing"
    )

    record = draft.draft_one(promo, channel)

    assert calls == [("authenticated", "https://winplus.heart.co.uk/competition/1/win-a-thing")]
    assert record.status == EntryStatus.SKIPPED


def test_draft_one_fails_closed_when_global_win_credentials_are_unset(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "GLOBAL_PLAYER_EMAIL", "")
    monkeypatch.setattr(config, "GLOBAL_PLAYER_PASSWORD", "")
    calls = _fake_openers(monkeypatch)
    promo, channel = _seed_promotion_and_channel(
        global_win.STATION_NAME, "https://winplus.heart.co.uk/competition/1/win-a-thing"
    )

    record = draft.draft_one(promo, channel)

    assert calls == []  # never even tried to open a browser
    assert record.status == EntryStatus.FAILED
    assert record.submission_error == "GLOBAL_PLAYER_EMAIL/PASSWORD not set"


# --- submit.py --------------------------------------------------------------


def test_submit_one_uses_anonymous_opener_for_a_non_global_win_promotion(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    _seed_user_profile()
    calls = _fake_openers(monkeypatch)
    monkeypatch.setattr(browser, "extract_form_fields", lambda page: [])
    monkeypatch.setattr(browser, "click_submit", _raise_no_submit_control)
    promo, channel = _seed_promotion_and_channel("Radio X", "https://example.com/radiox-comp")
    record = _seed_submittable_entry_record(promo, channel)

    result = submit.submit_one(record)

    assert calls == [("anonymous", "https://example.com/radiox-comp")]
    assert result.status == EntryStatus.FAILED
    assert result.submission_error == "stub: no submit control"


def test_submit_one_uses_authenticated_opener_for_a_global_win_promotion(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "GLOBAL_PLAYER_EMAIL", "test@example.com")
    monkeypatch.setattr(config, "GLOBAL_PLAYER_PASSWORD", "hunter2")
    _seed_user_profile()
    calls = _fake_openers(monkeypatch)
    monkeypatch.setattr(browser, "extract_form_fields", lambda page: [])
    monkeypatch.setattr(browser, "click_submit", _raise_no_submit_control)
    promo, channel = _seed_promotion_and_channel(
        global_win.STATION_NAME, "https://winplus.heart.co.uk/competition/1/win-a-thing"
    )
    record = _seed_submittable_entry_record(promo, channel)

    result = submit.submit_one(record)

    # The stub click_submit always fails — this test is only proving which
    # opener got called with which url, not exercising a real submit.
    assert calls == [("authenticated", "https://winplus.heart.co.uk/competition/1/win-a-thing")]
    assert result.status == EntryStatus.FAILED
    assert result.submission_error == "stub: no submit control"


def test_submit_one_fails_closed_when_global_win_credentials_are_unset(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "GLOBAL_PLAYER_EMAIL", "")
    monkeypatch.setattr(config, "GLOBAL_PLAYER_PASSWORD", "")
    _seed_user_profile()
    calls = _fake_openers(monkeypatch)
    promo, channel = _seed_promotion_and_channel(
        global_win.STATION_NAME, "https://winplus.heart.co.uk/competition/1/win-a-thing"
    )
    record = _seed_submittable_entry_record(promo, channel)

    result = submit.submit_one(record)

    assert calls == []  # never even tried to open a browser
    assert result.status == EntryStatus.FAILED
    assert result.submission_error == "GLOBAL_PLAYER_EMAIL/PASSWORD not set"


# --- Global Commercial routing — draft.py ----------------------------------


def test_draft_one_uses_commercial_opener_for_a_global_commercial_promotion(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "GLOBAL_COMMERCIAL_EMAIL", "test@example.com")
    monkeypatch.setattr(config, "GLOBAL_COMMERCIAL_PASSWORD", "hunter2")
    calls = _fake_openers(monkeypatch)
    monkeypatch.setattr(browser, "extract_form_fields", lambda page: [])
    promo, channel = _seed_promotion_and_channel(
        global_commercial.STATION_NAME, "https://comp.smoothradio.com/nescafe-2026/8"
    )

    record = draft.draft_one(promo, channel)

    assert calls == [("commercial", "https://comp.smoothradio.com/nescafe-2026/8")]
    assert record.status == EntryStatus.SKIPPED


def test_draft_one_fails_closed_when_global_commercial_credentials_are_unset(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "GLOBAL_COMMERCIAL_EMAIL", "")
    monkeypatch.setattr(config, "GLOBAL_COMMERCIAL_PASSWORD", "")
    calls = _fake_openers(monkeypatch)
    promo, channel = _seed_promotion_and_channel(
        global_commercial.STATION_NAME, "https://comp.smoothradio.com/nescafe-2026/8"
    )

    record = draft.draft_one(promo, channel)

    assert calls == []  # never even tried to open a browser
    assert record.status == EntryStatus.FAILED
    assert record.submission_error == "GLOBAL_COMMERCIAL_EMAIL/PASSWORD not set"


# --- Global Commercial routing — submit.py ---------------------------------


def test_submit_one_uses_commercial_opener_for_a_global_commercial_promotion(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "GLOBAL_COMMERCIAL_EMAIL", "test@example.com")
    monkeypatch.setattr(config, "GLOBAL_COMMERCIAL_PASSWORD", "hunter2")
    _seed_user_profile()
    calls = _fake_openers(monkeypatch)
    monkeypatch.setattr(browser, "extract_form_fields", lambda page: [])
    monkeypatch.setattr(browser, "click_submit", _raise_no_submit_control)
    promo, channel = _seed_promotion_and_channel(
        global_commercial.STATION_NAME, "https://comp.smoothradio.com/nescafe-2026/8"
    )
    record = _seed_submittable_entry_record(promo, channel)

    result = submit.submit_one(record)

    # The stub click_submit always fails — this test is only proving which
    # opener got called with which url, not exercising a real submit.
    assert calls == [("commercial", "https://comp.smoothradio.com/nescafe-2026/8")]
    assert result.status == EntryStatus.FAILED
    assert result.submission_error == "stub: no submit control"


def test_submit_one_fails_closed_when_global_commercial_credentials_are_unset(monkeypatch, tmp_path):
    _use_local_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "GLOBAL_COMMERCIAL_EMAIL", "")
    monkeypatch.setattr(config, "GLOBAL_COMMERCIAL_PASSWORD", "")
    _seed_user_profile()
    calls = _fake_openers(monkeypatch)
    promo, channel = _seed_promotion_and_channel(
        global_commercial.STATION_NAME, "https://comp.smoothradio.com/nescafe-2026/8"
    )
    record = _seed_submittable_entry_record(promo, channel)

    result = submit.submit_one(record)

    assert calls == []  # never even tried to open a browser
    assert result.status == EntryStatus.FAILED
    assert result.submission_error == "GLOBAL_COMMERCIAL_EMAIL/PASSWORD not set"
