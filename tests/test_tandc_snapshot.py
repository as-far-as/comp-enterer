"""
Tests against the same saved real fixtures the adapter tests use (talkSPORT
and Radio Exe detail pages) plus a couple of small synthetic HTML snippets
for the narrow phrasings the real fixtures don't happen to contain.
"""

from __future__ import annotations

from pathlib import Path

from radiocomp.compliance.tandc import parse_snapshot

FIXTURES = Path(__file__).parent / "fixtures"


def test_standard_rate_phrase_marks_free_route_true():
    html = (FIXTURES / "radioexe_detail_make_me_a_winner.html").read_text()
    snap = parse_snapshot(html, "promo-1")

    assert snap.parsed_free_route_exists is True
    assert snap.promotion_id == "promo-1"
    assert len(snap.raw_text) > 0


def test_complex_real_entry_limits_stay_unparsed_rather_than_guessed():
    # talkSPORT's real T&Cs here have genuinely complex, multi-channel
    # numeric limits ("up to a maximum of 100 times Online", "£40 on paid
    # SMS entries") — no simple phrase to extract, so this should stay
    # None rather than latching onto a partial, misleading match.
    html = (FIXTURES / "talksport_detail_nba_trip.html").read_text()
    snap = parse_snapshot(html, "promo-2")

    assert snap.parsed_entry_limit is None


def test_ambiguous_free_entry_phrase_in_a_paid_clause_is_not_mistaken_for_a_free_route():
    # This exact fixture's "free entry" mention sits inside a *paid*
    # boost-offer clause (see module docstring) — parse_snapshot doesn't
    # treat the bare phrase "free entry" as evidence at all, precisely
    # because of this real ambiguity. It still correctly finds
    # "standard network rate" elsewhere on the same page.
    html = (FIXTURES / "talksport_detail_nba_trip.html").read_text()
    snap = parse_snapshot(html, "promo-3")

    assert "free entry" in snap.raw_text.lower()
    assert snap.parsed_free_route_exists is True


def test_simple_entry_limit_phrase_is_captured_when_actually_present():
    html = "<html><body><main>Terms: one entry per household applies to this promotion.</main></body></html>"
    snap = parse_snapshot(html, "promo-4")

    assert snap.parsed_entry_limit is not None
    assert "household" in snap.parsed_entry_limit.lower()


def test_no_recognised_phrases_leaves_both_fields_none_not_false():
    html = "<html><body><main>Enter now for your chance to win a mystery prize.</main></body></html>"
    snap = parse_snapshot(html, "promo-5")

    assert snap.parsed_free_route_exists is None
    assert snap.parsed_entry_limit is None


def test_hash_is_deterministic_and_content_sensitive():
    html_a = "<html><body><main>Same text</main></body></html>"
    html_b = "<html><body><main>Different text</main></body></html>"

    snap_a1 = parse_snapshot(html_a, "promo-6")
    snap_a2 = parse_snapshot(html_a, "promo-6")
    snap_b = parse_snapshot(html_b, "promo-6")

    assert snap_a1.raw_text_hash == snap_a2.raw_text_hash
    assert snap_a1.raw_text_hash != snap_b.raw_text_hash
