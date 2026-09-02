"""
Tests the STATIONS seed data itself (not seed()'s storage side-effects,
same convention as the aggregator tests only exercising the pure parsing
step — see test_loquax_adapter.py). seed()'s upsert-by-name / idempotency
behaviour is straightforward enough, and storage-touching enough, to be
left to a live run rather than duplicating the repository layer's own
tests here.
"""

from __future__ import annotations

from radiocomp.stations.seed_local_independent import STATIONS


def test_no_duplicate_station_names():
    names = [s.name for s in STATIONS]
    assert len(names) == len(set(names))


def test_at_least_ten_stations_seeded():
    assert len(STATIONS) >= 10


def test_every_station_marked_local_independent():
    assert all(s.is_local_independent for s in STATIONS)


def test_every_station_has_a_live_checked_base_url():
    for s in STATIONS:
        assert len(s.base_urls) >= 1, f"{s.name} has no base_urls"
        assert all(url.startswith("https://") for url in s.base_urls), s.name


def test_no_ofcom_licence_ref_is_fabricated():
    # None of this data came from a real Ofcom lookup (that's the whole
    # reason this manual seed exists) — see the module docstring. A future
    # contributor adding a real licence ref should replace this seed data
    # rather than casually filling this field in.
    assert all(s.ofcom_licence_ref is None for s in STATIONS)


def test_every_station_discloses_manual_seeding_in_notes():
    for s in STATIONS:
        assert s.notes is not None and "Manually seeded" in s.notes, s.name
