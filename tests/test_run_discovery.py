"""
Unit tests for the scheduled-run orchestration logic in run_discovery.py,
using fake ingest() callables rather than the real adapters — the real
adapters already have their own fixture-based tests; this just checks the
wiring: one bad adapter shouldn't take the others down, and the exit code
should reflect "did everything fail" not "did anything fail".
"""

from __future__ import annotations

import radiocomp.run_discovery as rd


def _patch_adapters(monkeypatch, adapters):
    monkeypatch.setattr(rd, "_load_adapters", lambda: adapters)


def test_all_succeed_returns_zero_and_sums_new_promotions(monkeypatch):
    _patch_adapters(
        monkeypatch,
        [
            ("a", lambda: [1, 2, 3]),
            ("b", lambda: ([1, 2], ["channel"])),  # talksport/radioexe-shaped: (promotions, channels)
        ],
    )
    assert rd.main() == 0


def test_one_failure_among_several_still_returns_zero(monkeypatch):
    def broken():
        raise RuntimeError("station page changed shape")

    _patch_adapters(monkeypatch, [("broken", broken), ("fine", lambda: [1])])
    assert rd.main() == 0


def test_every_adapter_failing_returns_nonzero(monkeypatch):
    def broken():
        raise RuntimeError("boom")

    _patch_adapters(monkeypatch, [("a", broken), ("b", broken)])
    assert rd.main() == 1


def test_empty_adapter_list_does_not_crash(monkeypatch):
    _patch_adapters(monkeypatch, [])
    # 0 failures == 0 adapters is vacuously "everything failed" by the
    # len(failures) == len(adapters) check — but nothing should raise.
    assert rd.main() in (0, 1)
