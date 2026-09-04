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
            channels = [c for c in all_channels if c.promotion_id == promo.id]
            check = check_promotion(promo, all_promotions, entry_records)
            text, markup = build_notification(promo, channels, check)
            telegram_client.send_message(config.TELEGRAM_CHAT_ID, text, markup)
        except Exception:
            logger.exception("Failed to send Telegram notification for promotion %s", promo.id)
