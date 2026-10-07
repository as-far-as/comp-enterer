"""
The Instagram experiment's daily digest (docs/instagram-scoping-research.md,
sections 8 and 10) — a capped handful of giveaways a day, instead of
notify/send.py's one-message-per-new-promotion, which would have sent ~116
messages on the first ThePrizeFinder Instagram pass.

Once a day (the first scheduled discovery run at or after DIGEST_HOUR_UTC),
sends:
  - a header message: how many suggestions follow, plus a "check your
    Instagram DMs and Message Requests" reminder for any giveaway you
    entered whose draw is due — winners often get a 24-72h claim window,
    and promoters you don't follow land in Message Requests. Nothing here
    reads your DMs; it can only remind you to look.
  - up to DAILY_CAP suggestion messages, each with ✅ Entered / 🏷 Needs
    tags / ⏭ Skip buttons (handled in webhook/handlers.py). Entered then
    asks for the post's comment count as a one-tap range.

Selection, in order: Instagram post links only (ThePrizeFinder rows that
link to a Facebook post or a web page are left out — Instagram only, per
the user's decision), not closed, not already answered, never suggested
before. Promoters you've previously marked "needs tags" go last. Then
soonest-closing first, so nothing is suggested after it's too late; unknown
closing dates after dated ones. There's deliberately no "small promoters
first" ranking: the listing carries no follower or size signal, and
inventing one from promoter names would be a guess. The comment-count
answers are what will supply that signal.

Every unanswered suggestion is simply never shown again — an implicit skip,
rather than a backlog that grows every day you don't tap.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from .. import config
from ..aggregators.theprizefinder_instagram import instagram_shortcode
from ..models import DigestRecord, EntryChannel, EntryChannelType, EntryRecord, EntryStatus, Promotion
from ..storage.base import get_repository
from . import telegram_client
from .callback_data import build_callback_data

logger = logging.getLogger(__name__)

DAILY_CAP = 5
DIGEST_HOUR_UTC = 7  # 8am in summer, 7am in winter — no tz dependency in the container
DRAW_REMINDER_DAYS = (1, 2, 3)  # remind on each of the first 3 days after an entered giveaway closes


def select_suggestions(
    promotions: Iterable[Promotion],
    channels: Iterable[EntryChannel],
    entries: Iterable[EntryRecord],
    digests: Iterable[DigestRecord],
    today: date,
    cap: int = DAILY_CAP,
) -> list[tuple[Promotion, EntryChannel]]:
    instagram_channels = {c.promotion_id: c for c in channels if c.channel_type == EntryChannelType.INSTAGRAM}
    entries = list(entries)
    answered = {e.promotion_id for e in entries}
    already_suggested = {pid for d in digests for pid in d.promotion_ids}
    promo_by_id = {}
    candidates = []

    for promo in promotions:
        promo_by_id[promo.id] = promo
        channel = instagram_channels.get(promo.id)
        if channel is None or instagram_shortcode(promo.source_url) is None:
            continue
        if promo.entry_deadline is not None and promo.entry_deadline < today:
            continue
        if promo.id in answered or promo.id in already_suggested:
            continue
        candidates.append((promo, channel))

    tag_promoters = {
        promo_by_id[e.promotion_id].station_name_raw
        for e in entries
        if e.skip_reason == "needs_tags" and e.promotion_id in promo_by_id
    }

    candidates.sort(
        key=lambda pc: (
            pc[0].station_name_raw in tag_promoters,
            pc[0].entry_deadline is None,
            pc[0].entry_deadline or date.max,
        )
    )
    return candidates[:cap]


def draws_due(promotions: Iterable[Promotion], entries: Iterable[EntryRecord], today: date) -> list[Promotion]:
    entered = {
        e.promotion_id
        for e in entries
        if e.channel_type == EntryChannelType.INSTAGRAM and e.status == EntryStatus.SUBMITTED
    }
    due_deadlines = {today - timedelta(days=n) for n in DRAW_REMINDER_DAYS}
    return [p for p in promotions if p.id in entered and p.entry_deadline in due_deadlines]


def build_header(suggestion_count: int, due: list[Promotion]) -> str:
    lines = [f"📸 Instagram giveaways today: {suggestion_count}"]
    if suggestion_count:
        lines.append("Follow + like + comment only. Skip anything that needs tags, a story share, or a purchase.")
    if due:
        lines.append("")
        lines.append("🔔 Draws due — check your Instagram DMs, including Message Requests:")
        lines.extend(f"  • {p.title} ({_promoter(p)})" for p in due)
        lines.append("A real promoter never asks you to pay, or for card details, to claim a prize.")
    return "\n".join(lines)


def build_suggestion(promo: Promotion, channel: EntryChannel) -> tuple[str, dict]:
    closes = promo.entry_deadline.strftime("%a %d %b") if promo.entry_deadline else "unknown"
    text = f"{promo.title}\n{_promoter(promo)} · closes {closes}\n\n{promo.source_url}"
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Entered", "callback_data": build_callback_data("e", promo.id, channel.id)},
                {"text": "🏷 Needs tags", "callback_data": build_callback_data("t", promo.id, channel.id)},
                {"text": "⏭ Skip", "callback_data": build_callback_data("s", promo.id, channel.id)},
            ]
        ]
    }
    return text, reply_markup


def _promoter(promo: Promotion) -> str:
    # ThePrizeFinder suffixes every Instagram promoter with "(IG)" — stored
    # as seen, trimmed only for display.
    return promo.station_name_raw.removesuffix("(IG)").strip()


def send_daily_digest(now: Optional[datetime] = None) -> int:
    """Returns the number of suggestions sent (0 when it isn't time yet,
    already ran today, or Telegram isn't configured)."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return 0
    now = now or datetime.utcnow()
    if now.hour < DIGEST_HOUR_UTC:
        return 0

    today = now.date()
    digest_repo = get_repository("instagram_digests", DigestRecord)
    digests = list(digest_repo.list())
    if any(d.sent_on == today for d in digests):
        return 0

    promotions = list(get_repository("promotions", Promotion).list())
    channels = list(get_repository("entry_channels", EntryChannel).list())
    entries = list(get_repository("entry_records", EntryRecord).list())

    suggestions = select_suggestions(promotions, channels, entries, digests, today)
    due = draws_due(promotions, entries, today)

    # Recorded before sending, so a Telegram failure part-way through can't
    # make the next hourly run send the same digest again.
    digest_repo.add(DigestRecord(sent_on=today, promotion_ids=[p.id for p, _ in suggestions]))

    if not suggestions and not due:
        logger.info("Instagram digest: nothing to send today")
        return 0

    telegram_client.send_message(config.TELEGRAM_CHAT_ID, build_header(len(suggestions), due))
    for promo, channel in suggestions:
        text, reply_markup = build_suggestion(promo, channel)
        telegram_client.send_message(config.TELEGRAM_CHAT_ID, text, reply_markup=reply_markup)

    logger.info("Instagram digest: sent %d suggestion(s), %d draw reminder(s)", len(suggestions), len(due))
    return len(suggestions)
