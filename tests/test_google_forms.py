"""
find_embedded_form_url() against real fixtures: the two real talkSPORT
competition pages this was built for (captured live 2026-09-30, see
docs/build-log.md), plus a negative case using an existing normal
"How to Enter" page fixture that has no embedded Google Form at all.
"""

from __future__ import annotations

from pathlib import Path

from radiocomp.stations.google_forms import find_embedded_form_url

FIXTURES = Path(__file__).parent / "fixtures"


def test_finds_the_real_philadelphia_competition_form_url():
    html = (FIXTURES / "talksport_detail_philadelphia_google_form.html").read_text()
    url = find_embedded_form_url(html)
    assert url == (
        "https://docs.google.com/forms/d/e/1FAIpQLScni1cfdexRmiIFAXCFwdRYR0trUAvzqVVN11vYWgH3TM0XNg/viewform"
        "?usp=publish-editor"
    )


def test_finds_the_real_white_and_jordan_competition_form_url():
    html = (FIXTURES / "talksport_detail_whitejordan_google_form.html").read_text()
    url = find_embedded_form_url(html)
    assert url == (
        "https://docs.google.com/forms/d/e/1FAIpQLSce1a325PND5g2PArgIx806HXptW1FBg7kNDxJ1RGFELRFuWQ/viewform"
        "?usp=publish-editor"
    )


def test_returns_none_for_a_normal_how_to_enter_page_with_no_embedded_form():
    html = (FIXTURES / "talksport_detail_nba_trip.html").read_text()
    assert find_embedded_form_url(html) is None
