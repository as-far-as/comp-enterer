"""
Tests against a saved real HTML fixture
(tests/fixtures/theprizefinder_instagram_listing.html, page 0 of
/competitions/instagram-competitions captured live on 7 Oct 2026) rather
than the network. Re-capture it if ThePrizeFinder changes its markup and
these start failing for the wrong reason.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from radiocomp.aggregators.theprizefinder_instagram import (
    _last_page_index,
    _parse_deadline,
    instagram_dedup_hash,
    instagram_shortcode,
    parse_listing,
)
from radiocomp.models import EntryChannelType

FIXTURE = Path(__file__).parent / "fixtures" / "theprizefinder_instagram_listing.html"


def _parsed():
    return parse_listing(FIXTURE.read_text())


def test_parse_listing_extracts_expected_shape():
    parsed = _parsed()
    assert len(parsed) == 10  # 10 rows on page 0 when captured

    promo, channel = next(pc for pc in parsed if pc[0].title == "Win a Hadestown: The Musical merch bundle")
    assert promo.station_name_raw == "ODEON Cinemas(IG)"
    assert promo.entry_deadline == date(2026, 10, 13)
    assert promo.source_url == "https://www.instagram.com/p/DeJzTx0F-LC/"
    assert promo.discovered_via.value == "aggregator"
    assert channel.promotion_id == promo.id
    assert channel.channel_url_or_number == promo.source_url
    assert channel.raw_excerpt == "Enter via Instagram | UK Residents only"


def test_every_channel_is_instagram_and_unclassified():
    # The listing never says which mechanic a post uses (tags? must buy?),
    # so nothing may come back confidently free — see CLAUDE.md.
    for _, channel in _parsed():
        assert channel.channel_type == EntryChannelType.INSTAGRAM
        assert channel.is_free_route is None
        assert channel.review_recommended is True


def test_post_urls_are_canonicalised_across_observed_shapes():
    # The fixture has /p/ID, /username/p/ID/, and ?hl= / ?img_index= variants.
    by_title = {p.title: p for p, _ in _parsed()}
    assert by_title["Win a Beau & Elliot insulated travel mug"].source_url == "https://www.instagram.com/p/Dd8wtsWF5dY/"
    assert by_title["Win a selection of Baxters favourites"].source_url == "https://www.instagram.com/p/Dd6krvCihXQ/"
    assert by_title["Win a High Stora Way Storage"].source_url == "https://www.instagram.com/p/DeKi3XPF8Ou/"
    assert by_title["Win a boo basket"].source_url == "https://www.instagram.com/p/DdoTChcgOdu/"


def test_dedup_hash_is_keyed_on_shortcode_so_forwarded_links_match():
    promo = next(p for p, _ in _parsed() if p.title == "Win a Beau & Elliot insulated travel mug")
    forwarded = "https://www.instagram.com/p/Dd8wtsWF5dY/?igsh=abc123"
    assert promo.dedup_hash == instagram_dedup_hash(instagram_shortcode(forwarded))


def test_shortcode_parsing():
    assert instagram_shortcode("https://www.instagram.com/reel/Cxyz_12-3/") == "Cxyz_12-3"
    assert instagram_shortcode("https://www.instagram.com/rugsdirectuk/p/Dd3OQcTl8NM/") == "Dd3OQcTl8NM"
    assert instagram_shortcode("https://www.instagram.com/rugsdirectuk/") is None
    assert instagram_shortcode("https://example.com/p/abc/") is None


def test_deadline_parsing_handles_time_suffixes_and_garbage():
    assert _parse_deadline("08-10-2026 3pm") == date(2026, 10, 8)
    assert _parse_deadline("13-10-2026 Midnight") == date(2026, 10, 13)
    assert _parse_deadline("31-02-2026 Midnight") is None
    assert _parse_deadline("Ongoing") is None


def test_row_without_a_post_link_is_kept_not_dropped():
    html = FIXTURE.read_text().replace(
        "https://www.instagram.com/p/DeJzTx0F-LC/", "https://www.instagram.com/odeoncinemas/"
    )
    promo = next(p for p, _ in parse_listing(html) if p.title == "Win a Hadestown: The Musical merch bundle")
    assert promo.source_url == "https://www.instagram.com/odeoncinemas/"


def test_distinct_rows_get_distinct_dedup_hashes():
    parsed = _parsed()
    assert len({p.dedup_hash for p, _ in parsed}) == len(parsed)


def test_last_page_index_read_from_pager():
    soup = BeautifulSoup(FIXTURE.read_text(), "html.parser")
    assert _last_page_index(soup) == 11
