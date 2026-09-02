"""
Tests against a saved real HTML fixture
(tests/fixtures/theprizefinder_radio_search.html, captured live on 2 Sept
2026 from /search/competitions?keys=radio) rather than the network, so
these run offline and stay stable even if the live results change day to
day. Re-capture the fixture if ThePrizeFinder ever changes its page
structure and these tests start failing for the wrong reason.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from radiocomp.aggregators.theprizefinder import parse_listing

FIXTURE = Path(__file__).parent / "fixtures" / "theprizefinder_radio_search.html"


def test_parse_listing_extracts_expected_shape():
    html = FIXTURE.read_text()
    promotions = parse_listing(html)

    assert len(promotions) == 9  # 9 rows observed live for the "radio" search

    getaway = next(p for p in promotions if p.title == "Win the Ultimate Luxury Getaway to New York City for TWO")
    assert getaway.station_name_raw == "Virgin Radio"
    assert getaway.entry_deadline == date(2026, 9, 14)
    assert getaway.source_url == "https://www.theprizefinder.com/link-track?id=834518"
    assert getaway.discovered_via.value == "aggregator"


def test_promoter_text_excludes_nested_more_competitions_link():
    html = FIXTURE.read_text()
    promotions = parse_listing(html)

    for p in promotions:
        assert "more competitions" not in p.station_name_raw.lower()


def test_keyword_search_false_positives_are_captured_not_filtered():
    # "Radio Times" is a listings magazine, not a broadcast station, but it
    # matches the "radio" keyword search live on the site. This adapter
    # deliberately doesn't try to guess it out — see the module docstring —
    # so it should come through like any other promoter, for a downstream
    # normalizer step to resolve (or not) against real Station records.
    html = FIXTURE.read_text()
    promotions = parse_listing(html)

    assert any(p.station_name_raw == "Radio Times" for p in promotions)


def test_distinct_promotions_get_distinct_dedup_hashes():
    html = FIXTURE.read_text()
    promotions = parse_listing(html)

    assert len({p.dedup_hash for p in promotions}) == len(promotions)
