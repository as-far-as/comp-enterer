"""
The cross-brand-duplicate test reuses ThePrizeFinder's own real fixture
(tests/fixtures/theprizefinder_radio_search.html) rather than synthetic
data — it happens to contain a genuine live example of exactly the
situation spec section 4 describes: the same £4,000 TUI gift card
promotion listed once under Smooth Radio and once under Radio X, both
Global brands, both closing 2026-09-30 (see theprizefinder.py's own module
docstring and docs/build-log.md for how this was found).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from radiocomp.aggregators.theprizefinder import parse_listing
from radiocomp.compliance.engine import check_promotion, find_cross_brand_duplicates, shared_network_for
from radiocomp.models import DiscoveredVia, EntryChannelType, EntryRecord, EntryStatus, Promotion
from radiocomp.dedup import promotion_dedup_hash

FIXTURE = Path(__file__).parent / "fixtures" / "theprizefinder_radio_search.html"


def _promotions_from_fixture() -> list[Promotion]:
    return parse_listing(FIXTURE.read_text())


def test_shared_network_membership():
    assert shared_network_for("Radio X") == "Global"
    assert shared_network_for("Smooth Radio") == "Global"
    assert shared_network_for("smooth") == "Global"  # case/whitespace-insensitive
    assert shared_network_for("Kiss") == "Bauer"
    assert shared_network_for("Virgin Radio") is None
    assert shared_network_for("Radio Times") is None  # not a real station at all — see theprizefinder.py


def test_real_tui_giftcard_promotions_are_found_as_cross_brand_duplicates():
    promotions = _promotions_from_fixture()
    tui_promos = [p for p in promotions if "TUI" in p.title]
    assert len(tui_promos) == 2  # Smooth Radio + Radio X, differently capitalised titles

    smooth_promo = next(p for p in tui_promos if p.station_name_raw == "Smooth Radio")
    duplicates = find_cross_brand_duplicates(smooth_promo, promotions)

    assert len(duplicates) == 1
    assert duplicates[0].station_name_raw == "Radio X"


def test_unrelated_promotions_are_not_flagged_as_duplicates():
    promotions = _promotions_from_fixture()
    virgin_promo = next(p for p in promotions if p.station_name_raw == "Virgin Radio")

    assert find_cross_brand_duplicates(virgin_promo, promotions) == []


def test_same_network_same_title_but_different_deadline_is_not_a_duplicate():
    a = Promotion(
        station_name_raw="Heart",
        title="Win a Car",
        entry_deadline=date(2026, 10, 1),
        discovered_via=DiscoveredVia.DIRECT,
        source_url="https://example.com/a",
        dedup_hash=promotion_dedup_hash("Heart", "Win a Car", date(2026, 10, 1)),
    )
    b = Promotion(
        station_name_raw="Capital",
        title="Win a Car",
        entry_deadline=date(2026, 11, 1),
        discovered_via=DiscoveredVia.DIRECT,
        source_url="https://example.com/b",
        dedup_hash=promotion_dedup_hash("Capital", "Win a Car", date(2026, 11, 1)),
    )
    assert find_cross_brand_duplicates(a, [a, b]) == []


def test_already_entered_blocks_but_skipped_and_failed_do_not():
    promo = Promotion(
        station_name_raw="Virgin Radio",
        title="Win a Trip",
        discovered_via=DiscoveredVia.DIRECT,
        source_url="https://example.com/trip",
        dedup_hash=promotion_dedup_hash("Virgin Radio", "Win a Trip", None),
    )

    submitted = EntryRecord(promotion_id=promo.id, channel_type=EntryChannelType.WEB_FORM, status=EntryStatus.SUBMITTED)
    check = check_promotion(promo, [promo], [submitted])
    assert check.already_entered is True
    assert check.blocks_new_entry is True

    skipped = EntryRecord(promotion_id=promo.id, channel_type=EntryChannelType.WEB_FORM, status=EntryStatus.SKIPPED)
    failed = EntryRecord(promotion_id=promo.id, channel_type=EntryChannelType.WEB_FORM, status=EntryStatus.FAILED)
    check2 = check_promotion(promo, [promo], [skipped, failed])
    assert check2.already_entered is False
    assert check2.blocks_new_entry is False


def test_check_promotion_note_names_the_network_and_duplicate_id():
    promotions = _promotions_from_fixture()
    smooth_promo = next(p for p in promotions if p.station_name_raw == "Smooth Radio" and "TUI" in p.title)

    check = check_promotion(smooth_promo, promotions, [])

    assert check.shared_limit_network == "Global"
    assert check.blocks_new_entry is True
    assert "Global" in check.note
