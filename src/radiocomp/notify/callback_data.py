"""
Encode/decode the callback_data string carried on every inline button this
project sends — Approve/Skip, draft Submit/Reject, and outcome Won/No.
Telegram caps callback_data at 64 bytes — this format
("a:<12-char id>:<12-char id>") comes to 27 bytes, comfortably inside that
with room to spare if the format ever grows a version prefix.

The second id's meaning depends on the action, deliberately kept generic
rather than typed per-action: for "a"/"s" (Approve/Skip, including a
draft's Submit/Reject — same action letters, see webhook/handlers.py) it's
a channel_id; for "w"/"l" (outcome Won/lost) it's an entry_id. Callers know
which from the action itself.
"""

from __future__ import annotations

from typing import Optional

_APPROVE = "a"
_SKIP = "s"
_WON = "w"
_LOST = "l"
_VALID_ACTIONS = {_APPROVE, _SKIP, _WON, _LOST}


def build_callback_data(action: str, id1: str, id2: str) -> str:
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown action {action!r}, expected one of {_VALID_ACTIONS}")
    return f"{action}:{id1}:{id2}"


def parse_callback_data(data: str) -> Optional[tuple[str, str, str]]:
    """Returns (action, id1, id2), or None if data isn't a recognisable
    callback_data string — never raises. A malformed/stale callback is
    expected to happen eventually (an old message from a since-deleted
    record, a manual poke at the endpoint) and should be handled, not
    crash the webhook."""
    parts = data.split(":")
    if len(parts) != 3:
        return None
    action, id1, id2 = parts
    if action not in _VALID_ACTIONS or not id1 or not id2:
        return None
    return action, id1, id2
