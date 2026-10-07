"""
Local JSON-backed repository — the default today. One file per
"collection" under data/, e.g. data/promotions.json. Deliberately dumb
(reads the whole file, rewrites the whole file) because at personal-scale
data volumes that's fast enough and it means zero moving parts while
you're building and testing the discovery pipeline before the GCP
project exists.

Swapping to Firestore later (storage/firestore_store.py) is a drop-in —
nothing outside storage/ changes, since both implement the same
Repository protocol keyed by `id`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional, Type, TypeVar

from pydantic import BaseModel

from .. import config

ModelT = TypeVar("ModelT", bound=BaseModel)


class LocalJsonRepository:
    def __init__(self, collection_name: str, model_cls: Type[ModelT]):
        self.model_cls = model_cls
        self.path: Path = config.LOCAL_DATA_DIR / f"{collection_name}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}")

    def _read_all(self) -> dict[str, dict]:
        return json.loads(self.path.read_text() or "{}")

    def _write_all(self, data: dict[str, dict]) -> None:
        self.path.write_text(json.dumps(data, indent=2, default=str))

    def add(self, item: ModelT) -> None:
        data = self._read_all()
        item_id = getattr(item, "id", None)
        if item_id is None:
            raise ValueError(f"{self.model_cls.__name__} has no 'id' field to key on")
        data[item_id] = json.loads(item.model_dump_json())
        self._write_all(data)

    def get(self, item_id: str) -> Optional[ModelT]:
        data = self._read_all()
        raw = data.get(item_id)
        return self.model_cls.model_validate(raw) if raw else None

    def list(self) -> Iterable[ModelT]:
        data = self._read_all()
        return [self.model_cls.model_validate(raw) for raw in data.values()]

    def upsert(self, item: ModelT) -> None:
        self.add(item)  # add() already overwrites by id

    def delete(self, item_id: str) -> bool:
        data = self._read_all()
        if item_id not in data:
            return False
        del data[item_id]
        self._write_all(data)
        return True
