from __future__ import annotations

import pytest

from radiocomp.notify.callback_data import build_callback_data, parse_callback_data


def test_round_trip():
    data = build_callback_data("a", "abc123456789", "def987654321")
    assert parse_callback_data(data) == ("a", "abc123456789", "def987654321")


def test_stays_under_telegrams_64_byte_limit():
    data = build_callback_data("a", "abc123456789", "def987654321")
    assert len(data.encode("utf-8")) <= 64


def test_unknown_action_raises_on_build():
    with pytest.raises(ValueError):
        build_callback_data("x", "abc123456789", "def987654321")


@pytest.mark.parametrize(
    "malformed",
    [
        "a:only-one-id",
        "a:too:many:parts:here",
        "x:abc123456789:def987654321",  # unknown action
        "a::def987654321",  # empty promotion id
        "a:abc123456789:",  # empty channel id
        "",
        "not-callback-data-at-all",
    ],
)
def test_malformed_input_returns_none_not_raises(malformed):
    assert parse_callback_data(malformed) is None
