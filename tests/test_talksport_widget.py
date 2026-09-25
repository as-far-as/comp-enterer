"""
Pure-logic tests for stations/talksport_widget.py. fetch_widget_text()
itself needs a real browser against a real, live, third-party site — it
can't be meaningfully fixtured offline, so it's exercised only by a live
verification run (see docs/build-log.md), not here. What's tested here is
everything downstream of that: classification and the never-raise
fallback behaviour.
"""

from __future__ import annotations

from radiocomp.models import EntryChannel, EntryChannelType
from radiocomp.stations import talksport_widget

# The exact real text captured live from https://talksport.com/competitions/
# 4551832/win-the-ultimate-nba-trip-to-new-york-city-for-two/'s entry widget,
# 2026-09-08.
_REAL_PAID_WIDGET_TEXT = """x
LOGIN
06 d : 00 h : 11 m : 15 s
Win a trip for two to NYC to see the Knicks!

The more entries you have, the better your chances to Win A Trip For Two To Nyc To See The Knicks!

£2.50 PER ENTRY
£2.50 · x1
£10 · x5
£20 · x20
£30 · 100
BEST VALUE
1 entry to win!
YOUR TOTAL : £
2
.
5
0
ENTER NOWBy clicking Enter Now, you agree to the T&C's of this competition. 18+ UK only. This is a network promotion."""


def _ambiguous_channel(**overrides) -> EntryChannel:
    defaults = dict(
        promotion_id="p1",
        channel_type=EntryChannelType.WEB_FORM,
        is_free_route=None,
        review_recommended=True,
    )
    defaults.update(overrides)
    return EntryChannel(**defaults)


def test_classify_real_paid_widget_text():
    is_free, cost = talksport_widget.classify_widget_text(_REAL_PAID_WIDGET_TEXT)
    assert is_free is False
    assert cost == 2.50


def test_classify_synthetic_free_indicator_text():
    # No real free-widget example has been seen yet — synthetic, flagged
    # as unverified against reality in the module's own docstring.
    is_free, cost = talksport_widget.classify_widget_text("FREE TO ENTER — no purchase necessary!")
    assert is_free is True
    assert cost == 0.0


def test_classify_unmatched_text_returns_none_none():
    is_free, cost = talksport_widget.classify_widget_text("Please wait while we load your competition...")
    assert is_free is None
    assert cost is None


def test_resolve_online_channel_keeps_static_when_widget_never_appears(monkeypatch):
    monkeypatch.setattr(talksport_widget, "fetch_widget_text", lambda url: None)
    static = _ambiguous_channel()

    result = talksport_widget.resolve_online_channel("https://example.com", static)

    assert result is static


def test_resolve_online_channel_keeps_static_when_fetch_raises(monkeypatch):
    def _boom(url):
        raise RuntimeError("playwright timeout")

    monkeypatch.setattr(talksport_widget, "fetch_widget_text", _boom)
    static = _ambiguous_channel()

    result = talksport_widget.resolve_online_channel("https://example.com", static)

    assert result is static


def test_resolve_online_channel_keeps_static_when_text_matches_nothing(monkeypatch):
    monkeypatch.setattr(talksport_widget, "fetch_widget_text", lambda url: "Please wait...")
    static = _ambiguous_channel()

    result = talksport_widget.resolve_online_channel("https://example.com", static)

    assert result is static


def test_fetch_widget_text_retries_and_returns_on_eventual_success(monkeypatch):
    calls = []

    def _flaky(url):
        calls.append(url)
        if len(calls) < 3:
            return None
        return _REAL_PAID_WIDGET_TEXT

    monkeypatch.setattr(talksport_widget, "_fetch_widget_text_once", _flaky)

    result = talksport_widget.fetch_widget_text("https://example.com")

    assert result == _REAL_PAID_WIDGET_TEXT
    assert len(calls) == 3


def test_fetch_widget_text_gives_up_after_all_attempts_return_none(monkeypatch):
    monkeypatch.setattr(talksport_widget, "_fetch_widget_text_once", lambda url: None)

    result = talksport_widget.fetch_widget_text("https://example.com", attempts=3)

    assert result is None


def test_fetch_widget_text_retries_through_a_transient_exception(monkeypatch):
    calls = []

    def _flaky(url):
        calls.append(url)
        if len(calls) < 2:
            raise RuntimeError("transient playwright error")
        return _REAL_PAID_WIDGET_TEXT

    monkeypatch.setattr(talksport_widget, "_fetch_widget_text_once", _flaky)

    result = talksport_widget.fetch_widget_text("https://example.com")

    assert result == _REAL_PAID_WIDGET_TEXT


def test_fetch_widget_text_raises_only_if_the_final_attempt_errors(monkeypatch):
    monkeypatch.setattr(
        talksport_widget, "_fetch_widget_text_once", lambda url: (_ for _ in ()).throw(RuntimeError("persistent"))
    )

    try:
        talksport_widget.fetch_widget_text("https://example.com", attempts=2)
        assert False, "expected RuntimeError to propagate"
    except RuntimeError as exc:
        assert str(exc) == "persistent"


def test_resolve_online_channel_updates_with_real_confirmed_paid_result(monkeypatch):
    monkeypatch.setattr(talksport_widget, "fetch_widget_text", lambda url: _REAL_PAID_WIDGET_TEXT)
    static = _ambiguous_channel()

    result = talksport_widget.resolve_online_channel("https://example.com", static)

    assert result.is_free_route is False
    assert result.cost_to_entrant_gbp == 2.50
    assert result.review_recommended is False
    assert result.id == static.id
    assert result.promotion_id == static.promotion_id
