"""
Cloud Storage-backed JSON repository — the same "one JSON blob per
collection, read-modify-write" shape as local_json.py, just with a GCS blob
instead of a local file. This exists because of a real, confirmed
constraint rather than a hypothetical one: this project's GCP org enforces
a Deny policy blocking *all* service-account Firestore access, including
Cloud Run's own runtime identity (confirmed by actually running a Cloud
Run Job against real Firestore, not just inferred — see docs/build-log.md,
2026-09-03). The same test against Cloud Storage worked fine from that
same runtime identity, so this is what Cloud Run Jobs use instead of
Firestore for now. Firestore stays available for local dev via your own
account's ADC, which was never blocked — only service accounts are.

Same caveat as local_json.py, worth being explicit about here since it
matters more once something runs on a schedule rather than by hand: this
does a full read-modify-write per call with no locking or optimistic-
concurrency check, so two overlapping writers to the same collection can
lose an update. Fine at this project's actual scale (one scheduled job at
a time), not fine if that ever changes — revisit with GCS's generation
preconditions (`if_generation_match`) if it does.
"""

from __future__ import annotations

import json
from typing import Iterable, Optional, Type, TypeVar

from pydantic import BaseModel

from .. import config

ModelT = TypeVar("ModelT", bound=BaseModel)


class GcsJsonRepository:
    def __init__(self, collection_name: str, model_cls: Type[ModelT]):
        from google.cloud import storage  # deferred import — only required if actually used

        self.model_cls = model_cls
        self._blob_name = f"{collection_name}.json"
        client = storage.Client(project=config.GCP_PROJECT_ID or None)
        self._bucket = client.bucket(config.GCS_BUCKET_NAME)

    def _read_all(self) -> dict[str, dict]:
        blob = self._bucket.blob(self._blob_name)
        if not blob.exists():
            return {}
        return json.loads(blob.download_as_text() or "{}")

    def _write_all(self, data: dict[str, dict]) -> None:
        blob = self._bucket.blob(self._blob_name)
        blob.upload_from_string(json.dumps(data, indent=2, default=str), content_type="application/json")

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
