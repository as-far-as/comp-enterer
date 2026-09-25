"""
The hard-coded safety filter for what the entry-execution engine is
allowed to touch. channel_type == WEB_FORM is asserted as its own
standalone condition everywhere in this module — never inferred from
is_free_route/review_recommended alone. Those two fields say nothing
about the phone/post automation ban on their own: real data has already
shown "qualifying" (is_free_route=True, review_recommended=False)
channels that are POST or PHONE_ENTRY, both explicitly non-automatable
per CLAUDE.md's non-negotiable constraints (no phone automation, ever;
nothing here can post a letter). Every query below checks channel_type
independently as its own line, not folded into a combined boolean, so a
future edit to the free/review logic can never accidentally widen what
gets automated.
"""

from __future__ import annotations

from ..models import EntryChannel, EntryChannelType, EntryRecord, EntryStatus, Promotion


def find_draftable_channels(
    promotions: list[Promotion],
    channels: list[EntryChannel],
    entry_records: list[EntryRecord],
) -> list[tuple[Promotion, EntryChannel]]:
    """(Promotion, EntryChannel) pairs with nothing drafted for them yet."""
    already_has_record = {(r.promotion_id, r.channel_id) for r in entry_records}
    promo_by_id = {p.id: p for p in promotions}

    result: list[tuple[Promotion, EntryChannel]] = []
    for channel in channels:
        if channel.channel_type != EntryChannelType.WEB_FORM:
            continue
        if channel.is_free_route is not True or channel.review_recommended is not False:
            continue
        if (channel.promotion_id, channel.id) in already_has_record:
            continue
        promo = promo_by_id.get(channel.promotion_id)
        if promo is None:
            continue
        result.append((promo, channel))
    return result


def find_submittable_entries(entry_records: list[EntryRecord]) -> list[EntryRecord]:
    """EntryRecords that have been approved (a human tapped Submit on the
    drafted, screenshotted form) and are waiting for the actual submit."""
    return [
        r
        for r in entry_records
        if r.channel_type == EntryChannelType.WEB_FORM
        and r.status == EntryStatus.APPROVED
        and r.submitted_at is None
    ]
