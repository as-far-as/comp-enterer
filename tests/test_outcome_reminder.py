from __future__ import annotations

from datetime import date, timedelta

from radiocomp.models import DiscoveredVia, EntryChannelType, EntryRecord, EntryStatus, Outcome, Promotion
from radiocomp.outcomes.reminder import find_pending_outcome_checks


def _promo(**overrides) -> Promotion:
    defaults = dict(
        station_name_raw="Radio X",
        title="Win a Car",
        discovered_via=DiscoveredVia.DIRECT,
        source_url="https://example.com/win-a-car",
        dedup_hash="hash1",
    )
    defaults.update(overrides)
    return Promotion(**defaults)


def _entry(promo_id: str, **overrides) -> EntryRecord:
    defaults = dict(
        promotion_id=promo_id, channel_type=EntryChannelType.WEB_FORM, channel_id="c1", status=EntryStatus.SUBMITTED
    )
    defaults.update(overrides)
    return EntryRecord(**defaults)


def test_submitted_entry_past_deadline_and_buffer_is_pending():
    promo = _promo(entry_deadline=date.today() - timedelta(days=10))
    entry = _entry(promo.id)
    result = find_pending_outcome_checks([entry], [promo], [])
    assert result == [(entry, promo)]


def test_deadline_within_the_announce_buffer_is_not_yet_pending():
    promo = _promo(entry_deadline=date.today() - timedelta(days=1))
    entry = _entry(promo.id)
    assert find_pending_outcome_checks([entry], [promo], []) == []


def test_promotion_with_no_deadline_is_never_flagged():
    promo = _promo(entry_deadline=None)
    entry = _entry(promo.id)
    assert find_pending_outcome_checks([entry], [promo], []) == []


def test_non_submitted_entry_is_not_flagged():
    promo = _promo(entry_deadline=date.today() - timedelta(days=10))
    entry = _entry(promo.id, status=EntryStatus.APPROVED)
    assert find_pending_outcome_checks([entry], [promo], []) == []


def test_entry_with_an_existing_outcome_is_not_flagged_again():
    promo = _promo(entry_deadline=date.today() - timedelta(days=10))
    entry = _entry(promo.id)
    outcome = Outcome(entry_id=entry.id, won=True)
    assert find_pending_outcome_checks([entry], [promo], [outcome]) == []
