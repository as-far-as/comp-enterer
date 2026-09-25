"""
Manual seed for 4 real, currently-operating local/community stations whose
Ofcom-licensed broadcast area genuinely covers Southwark/Camberwell (SE5),
the user's actual home postcode — kept as its own file rather than
appended to seed_local_independent.py, since these were found for a
specific, documented reason (a real residency check) worth keeping
traceable separately from that file's original scattered UK-wide sample.

Context: every one of the 13 stations in seed_local_independent.py turned
out to be geographically irrelevant to the user (picked in Phase 0 without
regard to where they actually live) — a real competition found on one of
them (Central FM's genuinely free "Wake Up & Cash In") turned out to
require Forth Valley, Scotland residency, which the user doesn't have.
This file corrects that by targeting stations whose actual coverage area
includes SE5. Full investigation trail in docs/build-log.md, 2026-09-09.

All 4 were verified live (2026-09-09): real, currently-operating stations
with real websites, Ofcom community-licence coverage confirmed via
secondary sourcing (search-indexed licence summaries — the Ofcom Region-10
London PDF itself couldn't be read as text, a residual gap noted in the
build log). None had a live free competition at seed time — see each
station's own notes below. A fifth candidate, First Love Radio (aka FLR/
Fusion 107.3/Time 107.3/South London Radio), is confirmed defunct since
April 2009 and deliberately excluded.

Run this file directly to seed (idempotent — re-running upserts by name
rather than creating duplicates):
    python -m radiocomp.stations.seed_southeast_london
"""

from __future__ import annotations

import logging

from ..models import Station
from ..storage.base import get_repository

logger = logging.getLogger(__name__)

_SEED_NOTE = (
    "Manually seeded 2026-09-09 (see docs/build-log.md) specifically because its "
    "Ofcom community-licence coverage area includes Southwark/Camberwell (SE5)."
)

STATIONS: list[Station] = [
    Station(
        name="Select Radio",
        base_urls=["https://selectradioapp.com/"],
        is_local_independent=True,
        notes=(
            f"94.4FM. Covers Croydon, Southwark, Bromley, Lewisham, Greenwich, Bexley. "
            f"No Win/Competitions page found at seed time. {_SEED_NOTE}"
        ),
    ),
    Station(
        name="Rainbow Radio",
        base_urls=["https://www.rainbowradio.co.uk/"],
        is_local_independent=True,
        notes=(
            f"92.4FM + streaming. Covers Southwark, Lambeth, Lewisham, Croydon, western "
            f"Greenwich; based in Telegraph Hill/New Cross. Site is a pure client-rendered "
            f"SPA (empty <div id=\"root\">) — a future adapter would need Playwright, "
            f"confirmed live. No competition content found at seed time. {_SEED_NOTE}"
        ),
    ),
    Station(
        name="Mi-Soul",
        base_urls=["https://mi-soul.com/"],
        is_local_independent=True,
        notes=(
            f"24/7 soul music, DAB+/app/online + FM. Covers Lewisham, Southwark, Lambeth, "
            f"Greenwich. Only current prize mechanism at seed time was a VIP-ticket raffle "
            f"bundled with paid concert tickets (Soul II Soul, Mar 2026) — paid, not a free "
            f"giveaway. Plain-httpx-feasible (real HTML, no JS shell). {_SEED_NOTE}"
        ),
    ),
    Station(
        name="Resonance FM",
        base_urls=["https://www.resonancefm.com/"],
        is_local_independent=True,
        notes=(
            f"Arts-focused community station (London Musicians' Collective), studios "
            f"physically in Southwark (SE1). Historical competitions were ad hoc per-show "
            f"email giveaways (e.g. \"email bikeshow@resonancefm.com\"), not an ongoing Win "
            f"page — none currently live. Plain-httpx-feasible. {_SEED_NOTE}"
        ),
    ),
]


def seed() -> list[Station]:
    """Upsert STATIONS into the station repository, matching existing
    records by name so re-running this doesn't create duplicates. Returns
    the stations that were newly added (not already present by name)."""

    repo = get_repository("stations", Station)
    existing_by_name = {s.name: s for s in repo.list()}

    newly_added: list[Station] = []
    for station in STATIONS:
        existing = existing_by_name.get(station.name)
        if existing is not None:
            repo.upsert(station.model_copy(update={"id": existing.id}))
        else:
            repo.upsert(station)
            newly_added.append(station)

    logger.info(
        "South-East London station seed: %d in list, %d newly added, %d already present",
        len(STATIONS),
        len(newly_added),
        len(STATIONS) - len(newly_added),
    )
    return newly_added


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fresh = seed()
    print(f"\n{len(fresh)} new station(s) added:\n")
    for s in fresh:
        print(f"  - {s.name}")
