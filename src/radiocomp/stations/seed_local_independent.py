"""
Manual seed for the local/independent tier of the Station directory.

The spec's original plan (section 3) was to seed this tier from Ofcom's
public register of licensed radio services. That dataset turned out not to
be available in practice: Ofcom's own bulk technical-parameters CSVs (via
data.gov.uk) are dated March 2019 and their file URLs are now dead (404),
and the current ofcom.org.uk site only offers a "Look up radio station
details" tool that appears to be a single-record interactive lookup, not a
bulk export or API. Full investigation trail in docs/build-log.md,
2026-09-02. This file is the fallback the spec and README already
sanctioned: a manually-picked first tranche, seeded here instead of guessed
per-adapter later.

Every station below was checked live (its website was fetched and
confirmed to resolve to itself, showing content matching its name) before
being included — several initially-plausible candidates were dropped after
turning out to be dead domains, expired-domain squatters, or stations that
turned out to have been quietly absorbed into Bauer's Greatest Hits Radio
network since (e.g. Trax FM, Dearne FM, Ridings FM, Swansea Sound, Rutland
Radio all now redirect to hellorayo.co.uk/greatest-hits/<region> — they're
no longer independent, whatever older references say). None of this
amounts to Ofcom-verified data, though — no ofcom_licence_ref is set for
any of these, and "independent" here means "not Global / Bauer-Rayo /
News UK", checked by domain resolution only, not by looking up actual
licence ownership. Correct or extend this list as better information turns
up; treat it as a starting point, not an authoritative register.

Run this file directly to seed (idempotent — re-running upserts by name
rather than creating duplicates):
    python -m radiocomp.stations.seed_local_independent
"""

from __future__ import annotations

import logging

from ..models import Station
from ..storage.base import get_repository

logger = logging.getLogger(__name__)

_SEED_NOTE = (
    "Manually seeded 2026-09-02 (see docs/build-log.md) — Ofcom's register "
    "wasn't available in bulk/current form; not independently licence-verified."
)

STATIONS: list[Station] = [
    Station(
        name="Isle of Wight Radio",
        base_urls=["https://www.iwradio.co.uk"],
        is_local_independent=True,
        notes=_SEED_NOTE,
    ),
    Station(
        name="Central FM",
        base_urls=["https://www.centralfm.co.uk"],
        is_local_independent=True,
        notes=f"Falkirk, Scotland. {_SEED_NOTE}",
    ),
    Station(
        name="Drystone Radio",
        base_urls=["https://www.drystoneradio.com"],
        is_local_independent=True,
        notes=f"Skipton / Yorkshire Dales. {_SEED_NOTE}",
    ),
    Station(
        name="Banbury Sound",
        network="Adventure Radio Group",
        base_urls=["https://www.banburysound.co.uk"],
        is_local_independent=True,
        notes=_SEED_NOTE,
    ),
    Station(
        name="2BR",
        network="Adventure Radio Group",
        base_urls=["https://www.2br.co.uk"],
        is_local_independent=True,
        notes=f"Lancashire. {_SEED_NOTE}",
    ),
    Station(
        name="Energy FM",
        base_urls=["https://www.energyfm.net"],
        is_local_independent=True,
        notes=f"Isle of Man. {_SEED_NOTE}",
    ),
    Station(
        name="Manx Radio",
        base_urls=["https://www.manxradio.com"],
        is_local_independent=True,
        notes=f"Isle of Man's public service broadcaster (Manx Government-funded), not a "
        f"commercial independent in the usual sense, but outside Global/Bauer/News UK. {_SEED_NOTE}",
    ),
    Station(
        name="Bolton FM",
        base_urls=["https://www.boltonfm.com"],
        is_local_independent=True,
        notes=_SEED_NOTE,
    ),
    Station(
        name="KMFM",
        network="KM Group",
        base_urls=["https://www.kmfm.co.uk"],
        is_local_independent=True,
        notes=f"Kent — one shared brand across several KM Group town licences. {_SEED_NOTE}",
    ),
    Station(
        name="Susy Radio",
        base_urls=["https://www.susyradio.com"],
        is_local_independent=True,
        notes=f"Surrey. {_SEED_NOTE}",
    ),
    Station(
        name="Amber Sound FM",
        base_urls=["https://www.ambersoundfm.com"],
        is_local_independent=True,
        notes=f"Amber Valley, Derbyshire. {_SEED_NOTE}",
    ),
    Station(
        name="Insanity Radio",
        base_urls=["https://insanityradio.com"],
        is_local_independent=True,
        notes=f"103.2FM, South West London. {_SEED_NOTE}",
    ),
    Station(
        name="Angel Radio",
        base_urls=["https://www.angelradio.co.uk"],
        is_local_independent=True,
        notes=f"Havant, Hampshire. {_SEED_NOTE}",
    ),
    Station(
        name="Diverse FM",
        base_urls=["https://diversefm.com"],
        is_local_independent=True,
        notes=f"Luton. {_SEED_NOTE}",
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
            # Keep the existing id, refresh everything else from the seed list.
            repo.upsert(station.model_copy(update={"id": existing.id}))
        else:
            repo.upsert(station)
            newly_added.append(station)

    logger.info(
        "Station seed: %d in list, %d newly added, %d already present",
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
        print(f"  - {s.name}" + (f"  ({s.network})" if s.network else ""))
