"""
Tests against three real, saved talkSPORT competition pages (captured live
2 Sept 2026), chosen because they cover the three cases that matter most:
a straightforward SMS+Online+Post competition, one with a "Free phone
entry" channel (whose label is misleading — see talksport.py's docstring),
and a closed competition that should be skipped entirely.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from radiocomp.stations.talksport import parse_detail, parse_listing

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_listing_finds_real_competition_links():
    html = (FIXTURES / "talksport_listing.html").read_text()
    results = parse_listing(html)

    assert len(results) >= 15
    titles = [title for title, _ in results]
    assert "Chance to win £26,000 Tax-Free Cash!" in titles
    urls = [url for _, url in results]
    assert all(url.startswith("https://talksport.com/competitions/") for url in urls)
    assert len(urls) == len(set(urls))  # no duplicates


def test_tax_free_cash_prize_deadline_and_channels():
    html = (FIXTURES / "talksport_detail_26k_tax_free.html").read_text()
    promo, channels = parse_detail(html, "Chance to win £26,000 Tax-Free Cash!", "https://talksport.com/x")

    assert promo is not None
    assert promo.prize_value_gbp == 26000.0
    assert promo.station_name_raw == "talkSPORT"
    assert promo.entry_deadline == date(2026, 7, 20)

    by_type = {c.channel_type.value: c for c in channels}
    assert by_type["sms"].is_free_route is False
    assert by_type["sms"].cost_to_entrant_gbp == 2.50
    assert by_type["post"].is_free_route is True
    assert by_type["post"].cost_to_entrant_gbp == 0.0


def test_free_phone_entry_is_flagged_free_but_not_zero_confidence_risk():
    html = (FIXTURES / "talksport_detail_26k_2026_closed.html").read_text()
    # This fixture is a closed competition — parse_detail should skip it
    # entirely regardless of what its channels look like.
    promo, channels = parse_detail(html, "WIN £26,000 FOR 2026", "https://talksport.com/y")
    assert promo is None
    assert channels == []


def test_nba_trip_post_route_is_free_and_sms_is_paid():
    html = (FIXTURES / "talksport_detail_nba_trip.html").read_text()
    promo, channels = parse_detail(
        html, "Win the Ultimate NBA Trip to New York City for Two!", "https://talksport.com/z"
    )

    assert promo is not None
    by_type = {c.channel_type.value: c for c in channels}
    assert by_type["sms"].is_free_route is False
    assert by_type["post"].is_free_route is True

    # Nothing here should ever come back marked free with review_recommended
    # also True — that combination would mean "confidently free" and "not
    # confident" at once, which the classifier must never produce.
    for ch in channels:
        if ch.is_free_route is True:
            assert ch.review_recommended is False


# --- embedded-Google-Form template (no "How to Enter" heading at all) -----
#
# Two real competitions captured live 2026-09-30 (see docs/build-log.md),
# chosen because they're the ones that surfaced this gap: no "How to
# Enter" section at all, just prose pointing at an embedded Google Form.
# Confirmed live, at capture time, that neither page's own prose contains
# any free-indicator phrase ("free to enter", "no purchase necessary",
# "free of charge") anywhere near the form mention — so both are expected
# to come back ambiguous (is_free_route=None, review_recommended=True),
# which is the correct, conservative outcome here, not a gap in the test.


def test_philadelphia_competition_gets_a_web_form_channel_pointing_at_the_real_google_form():
    html = (FIXTURES / "talksport_detail_philadelphia_google_form.html").read_text()
    promo, channels = parse_detail(
        html, "WIN a trip to Philadelphia for two with Visit Pennsylvania!", "https://talksport.com/philadelphia"
    )

    assert promo is not None
    assert len(channels) == 1
    channel = channels[0]
    assert channel.channel_type.value == "web_form"
    # The real Google Form URL, not the talkSPORT page — this alone routes
    # entry-execution to the right page (draft.py/submit.py already do
    # `url = channel.channel_url_or_number or promo.source_url`).
    assert channel.channel_url_or_number == (
        "https://docs.google.com/forms/d/e/1FAIpQLScni1cfdexRmiIFAXCFwdRYR0trUAvzqVVN11vYWgH3TM0XNg/viewform"
        "?usp=publish-editor"
    )
    # Conservative classification: no free-indicator phrase was found live
    # on this real page, so this must stay ambiguous, never guessed free
    # just because it uses a Google Form.
    assert channel.is_free_route is None
    assert channel.review_recommended is True


def test_white_and_jordan_competition_gets_a_web_form_channel_pointing_at_the_real_google_form():
    html = (FIXTURES / "talksport_detail_whitejordan_google_form.html").read_text()
    promo, channels = parse_detail(html, "Win up to £1k on White & Jordan", "https://talksport.com/whitejordan")

    assert promo is not None
    assert len(channels) == 1
    channel = channels[0]
    assert channel.channel_type.value == "web_form"
    assert channel.channel_url_or_number == (
        "https://docs.google.com/forms/d/e/1FAIpQLSce1a325PND5g2PArgIx806HXptW1FBg7kNDxJ1RGFELRFuWQ/viewform"
        "?usp=publish-editor"
    )
    assert channel.is_free_route is None
    assert channel.review_recommended is True
