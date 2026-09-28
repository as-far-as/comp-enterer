"""
notify_new_promotions() — the public entrypoint called from
run_discovery.py (Cloud Run Job) and loquax.py's __main__ (GitHub Actions)
right after a discovery pass finds new promotions.
"""

from __future__ import annotations

import logging

from ..compliance.engine import check_promotion
from ..models import EntryChannel, EntryRecord, Promotion
from ..storage.base import get_repository
from .. import config
from . import telegram_client
from .message import build_notification

logger = logging.getLogger(__name__)


def _is_first_of_its_series(promo: Promotion, all_promotions: list[Promotion]) -> bool:
    """True unless promo is a later occurrence of an already-known
    recurring series (see models.Promotion.recurrence_series_id) —
    real, one-off promotions (recurrence_series_id is None) are always
    "first". Deliberately storage-driven rather than a new persisted
    "already notified" flag: the earliest entry_deadline among every
    stored promotion sharing this series id is the series' first
    occurrence, and that's the only one that gets notified, regardless
    of the order a discovery run happens to find them in (a first-ever
    run can discover several days of the same series in one pass — see
    docs/build-log.md, 2026-09-28). If no member of the series has a
    deadline to compare (shouldn't happen given the source always
    supplies one — see global_win.py), err on the side of notifying
    rather than silently dropping something real."""
    if not promo.recurrence_series_id:
        return True
    same_series = [p for p in all_promotions if p.recurrence_series_id == promo.recurrence_series_id]
    deadlines = [p.entry_deadline for p in same_series if p.entry_deadline is not None]
    if not deadlines:
        return True
    return promo.entry_deadline == min(deadlines)


def notify_new_promotions(promotions: list[Promotion]) -> None:
    if not promotions:
        return
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.info("Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset) — skipping notification")
        return

    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    entry_repo = get_repository("entry_records", EntryRecord)

    all_promotions = list(promo_repo.list())
    all_channels = list(channel_repo.list())
    entry_records = list(entry_repo.list())

    for promo in promotions:
        try:
            if not _is_first_of_its_series(promo, all_promotions):
                logger.info(
                    "Skipping notification for promotion %s — a later occurrence of recurring series %r "
                    "already has an earlier-deadline sibling notified",
                    promo.id,
                    promo.recurrence_series_id,
                )
                continue
            channels = [c for c in all_channels if c.promotion_id == promo.id]
            check = check_promotion(promo, all_promotions, entry_records)
            text, markup = build_notification(promo, channels, check)
            telegram_client.send_message(config.TELEGRAM_CHAT_ID, text, markup)
        except Exception:
            logger.exception("Failed to send Telegram notification for promotion %s", promo.id)
