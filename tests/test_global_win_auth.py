"""
Offline tests for entry_execution/global_win_auth.py's pure-ish pieces:
extract_competition_id() and _resolve_homepage_for_competition() (against
the same real fixtures test_global_win.py already uses — no live network
call in either).

sign_in()/open_authenticated_page()/_click_through_to_competition() are
inherently live-Playwright and not unit-tested here, matching
stations/talksport_widget.py's own precedent (its live-fetch functions
aren't unit-tested either) — see docs/build-log.md, 2026-09-28, for what
was verified live instead, and tests/test_entry_execution_routing.py for
the offline-testable routing logic in draft.py/submit.py that decides
*when* open_authenticated_page() gets called.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from radiocomp.entry_execution.global_win_auth import (
    _resolve_homepage_for_competition,
    extract_competition_id,
)

FIXTURES = Path(__file__).parent / "fixtures"
INIT = json.loads((FIXTURES / "heart_global_init.json").read_text())
LIST = json.loads((FIXTURES / "heart_global_competitions_list.json").read_text())


class _FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://winplus.heart.co.uk/")
            raise httpx.HTTPStatusError(
                "error", request=request, response=httpx.Response(self.status_code, request=request)
            )


class _FakeClient:
    """Maps URL -> canned JSON response, keyed loosely (substring match) —
    same technique as test_global_win.py's own _FakeClient."""

    def __init__(self, routes: dict):
        self.routes = routes

    def get(self, url, **kwargs):
        for key, data in self.routes.items():
            if key in url:
                return _FakeResponse(data)
        raise AssertionError(f"no fake route for {url}")


# --- extract_competition_id() -------------------------------------------


def test_extract_competition_id_from_a_real_shaped_url():
    url = "https://winplus.heart.co.uk/competition/13771/win-two-tickets-to-see-manic-street-preachers-and-suede"
    assert extract_competition_id(url) == 13771


def test_extract_competition_id_raises_on_a_url_with_no_competition_segment():
    with pytest.raises(ValueError):
        extract_competition_id("https://winplus.heart.co.uk/some-other-page")


# --- _resolve_homepage_for_competition() ---------------------------------


def test_resolves_homepage_for_a_real_non_heart_brand_competition():
    # id 13771, "Win Two Tickets to See Manic Street Preachers and Suede" —
    # real fixture data, brands: [67, 6] (Global Player + Radio X, no
    # Heart at all — see stations/global_win.py's own docstring). 67
    # (globalplayer) comes first in the real brands array, so that's the
    # homepage resolved, confirmed live 2026-09-28 to be a real, reachable
    # winplus subdomain.
    client = _FakeClient({"init.json": INIT, "list.json": LIST})

    homepage = _resolve_homepage_for_competition(client, 13771)

    assert homepage == "https://www.winplus.globalplayer.com/"


def test_resolves_homepage_for_a_competition_tagged_with_only_one_known_brand():
    # Synthetic listing (not the real fixture) constructed specifically to
    # prove resolution isn't hardcoded to whichever brand happens to
    # appear first in the real data (always globalplayer/bigtop40 there) —
    # here only radiox (id 6) is tagged, and it alone must resolve.
    listing = [{"id": 99001, "slug": "radiox-only-competition", "brands": [6]}]
    client = _FakeClient({"init.json": INIT, "list.json": listing})

    homepage = _resolve_homepage_for_competition(client, 99001)

    assert homepage == "https://www.winplus.radiox.co.uk/"


def test_raises_when_competition_id_is_not_in_the_listing_at_all():
    client = _FakeClient({"init.json": INIT, "list.json": LIST})

    with pytest.raises(RuntimeError, match="not found"):
        _resolve_homepage_for_competition(client, 9999999)


def test_raises_when_every_tagged_brand_has_no_known_homepage():
    # rivieraradio (id 100, brandRegion "world") is deliberately absent
    # from _BRAND_CODE_TO_HOMEPAGE — see global_win_auth.py's own
    # docstring. A competition tagged only with it must fail closed, never
    # guess a homepage.
    listing = [{"id": 99002, "slug": "riviera-only-competition", "brands": [100]}]
    client = _FakeClient({"init.json": INIT, "list.json": listing})

    with pytest.raises(RuntimeError, match="none of which"):
        _resolve_homepage_for_competition(client, 99002)
