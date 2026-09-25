"""
Unit tests for formatting.py's format_channel_line — shared by
view_promotions.py's CLI output and notify/message.py's Telegram text.
view_promotions.py's storage-reading main() is exercised live (local + real
GCS, see docs/build-log.md) rather than here, same convention as the
storage backends themselves.
"""

from __future__ import annotations

from radiocomp.formatting import format_channel_line as _format_channel
from radiocomp.models import EntryChannel, EntryChannelType


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


def test_phone_entry_shows_the_actual_number_to_call():
    # The real gap this closes: a genuinely free phone route was being
    # stored (channel_url_or_number) but never shown, so the user only
    # found one by clicking through and reading the source page themselves.
    line = _format_channel(
        _channel(
            channel_type=EntryChannelType.PHONE_ENTRY,
            is_free_route=True,
            cost_to_entrant_gbp=0.0,
            channel_url_or_number="0372 376 7519",
        )
    )
    assert "0372 376 7519" in line


def test_post_shows_the_actual_address():
    line = _format_channel(
        _channel(
            channel_type=EntryChannelType.POST,
            is_free_route=True,
            channel_url_or_number="PO Box 8162, Derby, DE1 9GU",
        )
    )
    assert "PO Box 8162, Derby, DE1 9GU" in line


def test_web_form_does_not_show_channel_url_since_its_just_the_source_url_again():
    line = _format_channel(
        _channel(
            channel_type=EntryChannelType.WEB_FORM,
            is_free_route=True,
            channel_url_or_number="https://example.com/campaign/FOO",
        )
    )
    assert "https://example.com" not in line


def test_missing_contact_info_shows_no_dash_placeholder():
    line = _format_channel(_channel(channel_type=EntryChannelType.PHONE_ENTRY, is_free_route=None))
    assert "—" not in line
