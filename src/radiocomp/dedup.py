"""Shared dedup-hash helper — see Promotion.dedup_hash in models.py."""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Optional


def promotion_dedup_hash(station_name_raw: str, title: str, deadline: Optional[date]) -> str:
    key = f"{station_name_raw.strip().lower()}|{title.strip().lower()}|{deadline.isoformat() if deadline else ''}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
