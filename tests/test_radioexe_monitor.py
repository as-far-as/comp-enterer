"""
Tests against saved real HTML fixtures (tests/fixtures/radioexe_*.html,
captured live on 2 Sept 2026 from nationplayer.com/radio-exe) rather than
the network — same convention as test_talksport_adapter.py. Re-capture the
fixtures if Radio Exe / Nation Player ever changes its page structure and
these tests start failing for the wrong reason.
"""

from __future__ import annotations

from pathlib import Path

from radiocomp.models import EntryChannelType
from radiocomp.stations.radioexe import _extract_channels, parse_detail, parse_listing

FIXTURES = Path(__file__).parent / "fixtures"
LISTING = FIXTURES / "radioexe_win_listing.html"
MAKE_ME_A_WINNER = FIXTURES / "radioexe_detail_make_me_a_winner.html"
CINEMA_TICKETS = FIXTURES / "radioexe_detail_cinema_tickets.html"


def test_parse_listing_finds_both_live_competitions():
    pairs = parse_listing(LISTING.read_text())

    assert len(pairs) == 2
    titles = [title for title, _ in pairs]
    assert "Make Me A Winner!" in titles
    assert "Free Film Friday" in titles
    for _, url in pairs:
        assert url.startswith("https://www.nationplayer.com/radio-exe/")


def test_multi_channel_competition_classifies_each_channel():
    _, url = next(p for p in parse_listing(LISTING.read_text()) if p[0] == "Make Me A Winner!")
    promo, channels = parse_detail(MAKE_ME_A_WINNER.read_text(), "Make Me A Winner!", url)

    assert promo.discovered_via.value == "direct"
    assert promo.station_name_raw == "Radio Exe"
    assert promo.network == "Nation Broadcasting"

    by_type = {c.channel_type: c for c in channels}

    web = by_type[EntryChannelType.WEB_FORM]
    assert web.is_free_route is False
    assert web.cost_to_entrant_gbp == 2.50

    sms = by_type[EntryChannelType.SMS]
    assert sms.is_free_route is False
    assert sms.cost_to_entrant_gbp == 2.50
    assert sms.channel_url_or_number == "65115"

    # Same Gambling-Act-compliant "standard rate" phone route as
    # talksport.py's PHONE_ENTRY handling — legitimately free-route, but
    # still a phone channel, so still must never be auto-dialled.
    phone = by_type[EntryChannelType.PHONE_ENTRY]
    assert phone.is_free_route is True
    assert phone.cost_to_entrant_gbp == 0.0
    assert phone.review_recommended is False


def test_whatsapp_and_email_channels_are_captured_and_flagged_for_review():
    _, url = next(p for p in parse_listing(LISTING.read_text()) if p[0] == "Free Film Friday")
    promo, channels = parse_detail(CINEMA_TICKETS.read_text(), "Free Film Friday", url)

    by_type = {c.channel_type: c for c in channels}

    assert EntryChannelType.WHATSAPP in by_type
    whatsapp = by_type[EntryChannelType.WHATSAPP]
    assert whatsapp.is_free_route is None
    assert whatsapp.review_recommended is True

    assert EntryChannelType.EMAIL in by_type
    email = by_type[EntryChannelType.EMAIL]
    assert email.channel_url_or_number == "studio@radioexe.co.uk"
    assert email.is_free_route is None
    assert email.review_recommended is True


def test_web_form_with_no_cost_phrase_is_flagged_ambiguous_not_silently_dropped():
    # Synthetic, not fixture-derived — no real free-web-form Radio Exe page
    # is on file (only the paid "Make Me A Winner!" example exists). Before
    # 2026-09-08, a page like this produced NO web_form channel at all
    # (silent omission); it should now come back ambiguous instead, giving
    # rendering.py's Playwright retry a real chance to resolve it.
    text = "You can enter this competition online using the form above. Good luck!"
    channels = _extract_channels(text)

    by_type = {c.channel_type: c for c in channels}
    assert EntryChannelType.WEB_FORM in by_type
    web = by_type[EntryChannelType.WEB_FORM]
    assert web.is_free_route is None
    assert web.review_recommended is True


def test_web_form_with_cost_phrase_still_takes_priority_over_presence_only():
    text = "You can enter this competition online using the form above. A single online entry costs £2.50."
    channels = _extract_channels(text)

    web = next(c for c in channels if c.channel_type == EntryChannelType.WEB_FORM)
    assert web.is_free_route is False
    assert web.cost_to_entrant_gbp == 2.50
    assert web.review_recommended is False


def test_no_fixed_deadline_stays_none_rather_than_guessed():
    # Both live competitions checked are recurring weekly promos with no
    # single fixed closing date stated ("Lines close Friday at 5pm" /
    # "Listen every Friday afternoon") — entry_deadline should stay None
    # rather than something invented from that recurring-day text.
    promo, _ = parse_detail(MAKE_ME_A_WINNER.read_text(), "Make Me A Winner!", "https://example.com")
    assert promo.entry_deadline is None
