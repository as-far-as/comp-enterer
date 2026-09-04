"""
Encode/decode the callback_data string carried on Approve/Skip inline
buttons. Telegram caps callback_data at 64 bytes — this format
("a:<12-char promotion id>:<12-char channel id>") comes to 27 bytes,
comfortably inside that with room to spare if the format ever grows a
version prefix.
"""

from __future__ import annotations

from typing import Optional

_APPROVE = "a"
_SKIP = "s"
_VALID_ACTIONS = {_APPROVE, _SKIP}


def build_callback_data(action: str, promotion_id: str, channel_id: str) -> str:
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown action {action!r}, expected one of {_VALID_ACTIONS}")
    return f"{action}:{promotion_id}:{channel_id}"


def parse_callback_data(data: str) -> Optional[tuple[str, str, str]]:
    """Returns (action, promotion_id, channel_id), or None if data isn't a
    recognisable callback_data string — never raises. A malformed/stale
    callback is expected to happen eventually (an old message from a
    since-deleted record, a manual poke at the endpoint) and should be
    handled, not crash the webhook."""
    parts = data.split(":")
    if len(parts) != 3:
        return None
    action, promotion_id, channel_id = parts
    if action not in _VALID_ACTIONS or not promotion_id or not channel_id:
        return None
    return action, promotion_id, channel_id
