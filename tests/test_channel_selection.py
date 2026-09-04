from __future__ import annotations

from radiocomp.models import EntryChannel, EntryChannelType
from radiocomp.notify.channel_selection import select_approvable_channel


def _channel(**overrides) -> EntryChannel:
    defaults = dict(promotion_id="p1", channel_type=EntryChannelType.WEB_FORM)
    defaults.update(overrides)
    return EntryChannel(**defaults)


def test_clean_free_channel_is_selected():
    ch = _channel(is_free_route=True, review_recommended=False)
    assert select_approvable_channel([ch]) is ch


def test_free_but_review_recommended_is_not_selected():
    ch = _channel(is_free_route=True, review_recommended=True)
    assert select_approvable_channel([ch]) is None


def test_paid_channel_is_not_selected():
    ch = _channel(is_free_route=False, cost_to_entrant_gbp=2.50)
    assert select_approvable_channel([ch]) is None


def test_unclassified_channel_is_not_selected():
    ch = _channel(is_free_route=None)
    assert select_approvable_channel([ch]) is None


def test_empty_list_returns_none():
    assert select_approvable_channel([]) is None


def test_first_qualifying_channel_wins_when_multiple_present():
    paid = _channel(is_free_route=False, cost_to_entrant_gbp=2.50)
    free = _channel(is_free_route=True, review_recommended=False)
    another_free = _channel(is_free_route=True, review_recommended=False)
    assert select_approvable_channel([paid, free, another_free]) is free
