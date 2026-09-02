"""
Tests against a saved real HTML fixture (tests/fixtures/loquax_radio_listing.html,
captured live on 2 Sept 2026) rather than the network, so these run offline and
stay stable even if the live listing changes day to day. Re-capture the fixture
if Loquax ever changes its page structure and these tests start failing for the
wrong reason.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from radiocomp.aggregators.loquax import parse_listing
from radiocomp.dedup import promotion_dedup_hash

FIXTURE = Path(__file__).parent / "fixtures" / "loquax_radio_listing.html"


def test_parse_listing_extracts_expected_shape():
    html = FIXTURE.read_text()
    promotions = parse_listing(html)

    assert len(promotions) >= 7  # 10 listing rows observed live, 4 of them the same promotion

    titles = [p.title for p in promotions]
    assert "Weekend in Edinburgh" in titles

    edinburgh = next(p for p in promotions if p.title == "Weekend in Edinburgh")
    assert edinburgh.entry_deadline == date(2026, 9, 11)
    assert edinburgh.source_url.startswith("https://www.loquax.co.uk/forums/threads/")
    assert edinburgh.discovered_via.value == "aggregator"


def test_repeated_listing_rows_collapse_to_one_dedup_hash():
    html = FIXTURE.read_text()
    promotions = parse_listing(html)

    tui_rows = [p for p in promotions if p.title == "£4,000 TUI Gift Card"]
    # Loquax listed this same thread 4 times live; parse_listing itself doesn't
    # dedup (that's ingest()'s job), but every row for the same promotion must
    # produce the same hash so ingest() *can* collapse them.
    assert len(tui_rows) == 4
    assert len({p.dedup_hash for p in tui_rows}) == 1


def test_dedup_hash_is_stable_and_sensitive_to_its_inputs():
    h1 = promotion_dedup_hash("Heart", "Cash Call", date(2026, 9, 30))
    h2 = promotion_dedup_hash("Heart", "Cash Call", date(2026, 9, 30))
    h3 = promotion_dedup_hash("Capital", "Cash Call", date(2026, 9, 30))

    assert h1 == h2
    assert h1 != h3
