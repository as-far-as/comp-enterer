"""
Compliance & eligibility engine — first pass (spec section 4).

Spec section 4 names two checks to run before anything gets entered: (1)
has this exact promotion already been entered, and (2) does it belong to a
network with a shared cross-brand limit (Global: one entry across Heart,
Capital, Smooth, Classic FM, LBC and Radio X combined; Bauer's Rayo-era
stable reads similarly) where a *different* promotion already covers the
same underlying competition. This module implements both as plain,
testable functions — there's no entry-execution engine yet (spec section
5) to actually gate, so nothing here blocks anything; it's meant to be run
against what's already been discovered, surfacing exactly the situation
spec section 4 describes so it's visible before that engine exists.

The cross-brand check is inherently a fuzzy match — the same shared
promotion shows up as separately-scraped Promotion rows per station, with
no shared identifier connecting them. This showed up for real, unprompted,
in ThePrizeFinder's own test fixture: "Win A £4,000 Travel Gift Card Thanks
To TUI" listed once under Smooth Radio and once (capitalised slightly
differently) under Radio X — both Global brands, both the same deadline,
almost certainly one promotion. Matching here is deliberately narrow
(exact title match once case/whitespace-normalised, same network, same
deadline when both have one) rather than fuzzy-string-similarity — a
missed match just means two separately-flagged promotions, which is safe;
a false match would incorrectly suppress a genuine second entry
opportunity, which isn't.

Network membership lists are intentionally short and only include stations
this session could confirm are still actually part of that stable as of
2026-09-02 (see docs/build-log.md) — several plausible-looking Bauer/Global
regional names turned out to have moved between groups or shut down when
checked live earlier this session. Extend these lists as you confirm more,
rather than guessing from station names alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from ..models import EntryRecord, EntryStatus, Promotion

# Keys are informal network labels (for the human-readable note), values are
# lower-cased station names sharing that network's cross-brand entry limit.
SHARED_LIMIT_NETWORKS: dict[str, frozenset[str]] = {
    "Global": frozenset(
        {
            "heart",
            "capital",
            "smooth",
            "smooth radio",
            "classic fm",
            "lbc",
            "radio x",
            # This adapter's own station_name_raw (see
            # stations/global_win.py) — needs to be a member here too, or
            # its own promotions would never be recognised as
            # Global-network by shared_network_for() at all. Same pattern
            # as "make me a winner (bauer)" below for Bauer.
            "global win",
        }
    ),
    "Bauer": frozenset(
        {
            "kiss",
            "absolute radio",
            "greatest hits radio",
            # Added 2026-09-09 alongside the Make Me A Winner adapter —
            # confirmed live (api.winhappy.com's own station carousel) as
            # current Bauer stations sharing that platform's competitions,
            # closing a gap this module's own docstring already flagged.
            "magic",
            "hits radio",
            "planet rock",
            # This adapter's own station_name_raw (see
            # stations/bauer_makemeawinner.py) — needs to be a member
            # here too, or its own promotions would never be recognised
            # as Bauer-network by shared_network_for() at all.
            "make me a winner (bauer)",
        }
    ),
}

# Entry states that represent an entry already made or in progress — FAILED
# and SKIPPED don't block a fresh attempt.
_BLOCKING_STATUSES = frozenset({EntryStatus.DRAFTED, EntryStatus.APPROVED, EntryStatus.SUBMITTED})


def _normalize_station(name: str) -> str:
    return name.strip().lower()


def _normalize_title(title: str) -> str:
    return " ".join(title.strip().lower().split())


def shared_network_for(station_name_raw: str) -> Optional[str]:
    normalized = _normalize_station(station_name_raw)
    for network, members in SHARED_LIMIT_NETWORKS.items():
        if normalized in members:
            return network
    return None


def already_entered(promotion: Promotion, entry_records: Iterable[EntryRecord]) -> bool:
    return any(r.promotion_id == promotion.id and r.status in _BLOCKING_STATUSES for r in entry_records)


def find_cross_brand_duplicates(promotion: Promotion, other_promotions: Iterable[Promotion]) -> list[Promotion]:
    """Other promotions likely to be the same underlying competition as
    `promotion`, entered under a different brand sharing its network's
    cross-brand limit. Empty if `promotion`'s own station isn't part of any
    known shared-limit network."""

    network = shared_network_for(promotion.station_name_raw)
    if network is None:
        return []

    target_title = _normalize_title(promotion.title)
    matches: list[Promotion] = []
    for other in other_promotions:
        if other.id == promotion.id:
            continue
        if shared_network_for(other.station_name_raw) != network:
            continue
        if _normalize_title(other.title) != target_title:
            continue
        if promotion.entry_deadline and other.entry_deadline and promotion.entry_deadline != other.entry_deadline:
            continue
        matches.append(other)
    return matches


@dataclass
class ComplianceCheck:
    promotion_id: str
    already_entered: bool
    shared_limit_network: Optional[str]
    cross_brand_duplicate_ids: list[str] = field(default_factory=list)

    @property
    def blocks_new_entry(self) -> bool:
        return self.already_entered or bool(self.cross_brand_duplicate_ids)

    @property
    def note(self) -> str:
        """Human-readable summary, suitable for EntryRecord.compliance_note
        once an entry-execution engine actually exists to write one."""
        if self.already_entered:
            return "Already entered (or in progress) — do not enter again."
        if self.cross_brand_duplicate_ids:
            return (
                f"Same competition already entered under a different {self.shared_limit_network} "
                f"brand (promotion id(s): {', '.join(self.cross_brand_duplicate_ids)}) — "
                f"{self.shared_limit_network}'s T&Cs limit this to one entry across the whole network."
            )
        return "No duplicate-entry or cross-brand conflict found."


def check_promotion(
    promotion: Promotion,
    all_promotions: Iterable[Promotion],
    entry_records: Iterable[EntryRecord],
) -> ComplianceCheck:
    duplicates = find_cross_brand_duplicates(promotion, all_promotions)
    return ComplianceCheck(
        promotion_id=promotion.id,
        already_entered=already_entered(promotion, entry_records),
        shared_limit_network=shared_network_for(promotion.station_name_raw),
        cross_brand_duplicate_ids=[d.id for d in duplicates],
    )
