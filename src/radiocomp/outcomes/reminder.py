"""
Results tracking (spec section 7), kept deliberately small: once a
SUBMITTED entry's promotion deadline has passed (plus a few days' buffer
for a station to actually announce a winner), ask once whether you won,
via the same Approve/Skip-style Telegram buttons ("w"/"l" — see
notify/callback_data.py) and webhook/handlers.py's outcome dispatch. No
further reminder sophistication than "ask once" — this can grow later if
it proves worth it.

Runs as the last step of run_entry_execution.py rather than standing up a
fourth piece of scheduled infrastructure for something this infrequent.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from .. import config
from ..models import EntryRecord, EntryStatus, Outcome, Promotion
from ..notify import telegram_client
from ..notify.callback_data import build_callback_data
from ..storage.base import get_repository

logger = logging.getLogger(__name__)

_ANNOUNCE_BUFFER_DAYS = 5  # give the station time to actually pick and announce a winner


def find_pending_outcome_checks(
    entries: list[EntryRecord], promotions: list[Promotion], outcomes: list[Outcome]
) -> list[tuple[EntryRecord, Promotion]]:
    """SUBMITTED entries whose promotion's deadline (plus the announce
    buffer) has passed and which have no Outcome yet. An entry whose
    promotion has no known entry_deadline is never flagged — there's no
    principled date to ask by, and guessing one risks asking before a
    winner could plausibly have been announced."""
    promo_by_id = {p.id: p for p in promotions}
    already_asked = {o.entry_id for o in outcomes}
    today = date.today()

    result = []
    for entry in entries:
        if entry.status != EntryStatus.SUBMITTED or entry.id in already_asked:
            continue
        promo = promo_by_id.get(entry.promotion_id)
        if promo is None or promo.entry_deadline is None:
            continue
        if today >= promo.entry_deadline + timedelta(days=_ANNOUNCE_BUFFER_DAYS):
            result.append((entry, promo))
    return result


def notify_pending_outcomes() -> int:
    entry_repo = get_repository("entry_records", EntryRecord)
    promo_repo = get_repository("promotions", Promotion)
    outcome_repo = get_repository("outcomes", Outcome)

    pending = find_pending_outcome_checks(list(entry_repo.list()), list(promo_repo.list()), list(outcome_repo.list()))
    for entry, promo in pending:
        _send_outcome_check(entry, promo)
    return len(pending)


def _send_outcome_check(entry: EntryRecord, promo: Promotion) -> None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    text = f"🏆 Did you win?\n{promo.title}\n{promo.station_name_raw}\n\n{promo.source_url}"
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "🏆 Won", "callback_data": build_callback_data("w", promo.id, entry.id)},
                {"text": "❌ Didn't win", "callback_data": build_callback_data("l", promo.id, entry.id)},
            ]
        ]
    }
    telegram_client.send_message(config.TELEGRAM_CHAT_ID, text, reply_markup=reply_markup)
    logger.info("Sent outcome check for entry %s (promotion %s)", entry.id, promo.id)
