"""
Shared test setup.

config.py loads .env at import time, and a developer .env sets
STORAGE_BACKEND=firestore — so any test that reached get_repository()
without overriding the backend itself was reading and writing the real
Firestore database (found 2026-10-07: test_global_commercial's ingest
tests "failed" because the real NESCAFÉ promotion was already stored
there, so it deduped to zero). This forces every test onto local JSON
storage in a fresh temp dir, whatever .env says. Tests that also set
these themselves keep working — their monkeypatch runs after this one.
"""

from __future__ import annotations

import pytest

from radiocomp import config


@pytest.fixture(autouse=True)
def _isolated_local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path / "data")
