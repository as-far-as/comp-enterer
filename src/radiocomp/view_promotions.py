"""
Read-only view of what's actually been discovered so far — the missing
piece flagged when Cloud Scheduler went live: the scheduled job now writes
real data every hour, but there was no way to actually look at it short of
`gcloud storage cat`-ing raw JSON. This is the smallest possible fix: no
dashboard, no notifications, no approve/skip (that's the Telegram bot from
spec section 6, not built yet) — just a readable list of what's known,
using whatever STORAGE_BACKEND is configured, same as every adapter.

Also runs each promotion through the compliance engine's checks (spec
section 4) so "already entered" / "same competition under another Global
brand" are visible here rather than needing a separate step.

Run it:
    python -m radiocomp.view_promotions
"""

from __future__ import annotations

from radiocomp.compliance.engine import check_promotion
from radiocomp.formatting import format_channel_line
from radiocomp.models import EntryChannel, EntryRecord, Promotion
from radiocomp.storage.base import get_repository


def main() -> None:
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    entry_repo = get_repository("entry_records", EntryRecord)

    promotions = list(promo_repo.list())
    channels = list(channel_repo.list())
    entries = list(entry_repo.list())

    if not promotions:
        print("Nothing discovered yet.")
        return

    # Soonest deadline first; undated (recurring/rolling) promotions last.
    promotions.sort(key=lambda p: (p.entry_deadline is None, p.entry_deadline))

    print(f"{len(promotions)} promotion(s) known:\n")

    for promo in promotions:
        deadline_str = promo.entry_deadline.isoformat() if promo.entry_deadline else "no fixed deadline"
        prize_str = f"£{promo.prize_value_gbp:,.0f}" if promo.prize_value_gbp else "prize value unclear"
        print(f"- {promo.title}")
        print(f"    {promo.station_name_raw}  |  {prize_str}  |  closes {deadline_str}  |  {promo.discovered_via.value}")

        promo_channels = [c for c in channels if c.promotion_id == promo.id]
        for ch in promo_channels:
            print(format_channel_line(ch))
        if not promo_channels:
            print("      (no entry channels recorded yet)")

        check = check_promotion(promo, promotions, entries)
        if check.blocks_new_entry:
            print(f"      !! {check.note}")

        print()


if __name__ == "__main__":
    main()
