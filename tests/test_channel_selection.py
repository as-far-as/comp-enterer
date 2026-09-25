from __future__ import annotations

from radiocomp.models import EntryChannel, EntryChannelType
from radiocomp.notify.channel_selection import select_approvable_channel


def _channel(**overrides) -> EntryChannel:
    # POST by default, not WEB_FORM — WEB_FORM is deliberately excluded by
    # select_approvable_channel (see test_web_form_channel_is_never_selected
    # below), so a default of WEB_FORM would make every other test in this
    # file silently test the wrong thing.
    defaults = dict(promotion_id="p1", channel_type=EntryChannelType.POST)
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


def test_web_form_channel_is_never_selected_even_when_clean_and_free():
    # WEB_FORM goes through entry_execution/'s own draft flow instead —
    # see this module's docstring. A clean, confidently-free web_form
    # channel must never get an immediate Approve/Skip button, or a tap
    # would create an unreviewed, undrafted APPROVED EntryRecord that the
    # entry-execution engine's submit stage could act on blindly.
    web_form = EntryChannel(
        promotion_id="p1",
        channel_type=EntryChannelType.WEB_FORM,
        is_free_route=True,
        review_recommended=False,
    )
    assert select_approvable_channel([web_form]) is None


def test_web_form_excluded_but_a_later_qualifying_channel_still_wins():
    web_form = EntryChannel(
        promotion_id="p1",
        channel_type=EntryChannelType.WEB_FORM,
        is_free_route=True,
        review_recommended=False,
    )
    post = _channel(is_free_route=True, review_recommended=False)
    assert select_approvable_channel([web_form, post]) is post
