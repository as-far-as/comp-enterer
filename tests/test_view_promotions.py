"""
Unit tests for view_promotions.py's formatting logic — the storage-reading
main() function is exercised live (local + real GCS, see docs/build-log.md)
rather than here, same convention as the storage backends themselves.
"""

from __future__ import annotations

from radiocomp.models import EntryChannel, EntryChannelType
from radiocomp.view_promotions import _format_channel


def _channel(**overrides) -> EntryChannel:
    defaults = dict(promotion_id="p1", channel_type=EntryChannelType.WEB_FORM)
    defaults.update(overrides)
    return EntryChannel(**defaults)


def test_free_channel_shows_free_flag():
    line = _format_channel(_channel(is_free_route=True, cost_to_entrant_gbp=0.0))
    assert "[FREE]" in line
    assert "£" not in line  # zero cost isn't worth printing


def test_paid_channel_shows_paid_flag_and_cost():
    line = _format_channel(_channel(is_free_route=False, cost_to_entrant_gbp=2.50))
    assert "[PAID]" in line
    assert "£2.50" in line


def test_unclassified_channel_shows_review_flag():
    line = _format_channel(_channel(is_free_route=None))
    assert "[REVIEW]" in line


def test_review_recommended_overrides_a_confident_classification():
    # Shouldn't happen in practice (review_recommended=True alongside a
    # confident is_free_route is a contradiction upstream), but if it does,
    # review must win — never silently show FREE/PAID over a flagged channel.
    line = _format_channel(_channel(is_free_route=True, review_recommended=True))
    assert "[REVIEW]" in line
