"""
Firestore-backed repository. Not wired up or tested yet — deliberately —
this file exists so the shape is ready the moment your GCP project does
too, but there was nothing to actually run it against yet.

To activate once you have a project:
  1. pip install google-cloud-firestore (uncomment it in requirements.txt)
  2. set GCP_PROJECT_ID and STORAGE_BACKEND=firestore in your .env
  3. `gcloud auth application-default login` (local dev) — no other
     credential wiring needed; google-cloud-firestore picks up ADC
     automatically, and inside a Cloud Run Job/Service it uses the
     runtime service account instead.

Note this needs one behavioural check before relying on it for real:
`.model_dump(mode="json")` turns date/datetime fields into ISO strings
rather than native Firestore Timestamp/Date types — fine for a first
pass, but worth revisiting when EntryRecord.submitted_at etc. need to be
queried/sorted by Firestore itself rather than just read back.
"""

from __future__ import annotations

from typing import Iterable, Optional, Type, TypeVar

from pydantic import BaseModel

from .. import config

ModelT = TypeVar("ModelT", bound=BaseModel)


class FirestoreRepository:
    def __init__(self, collection_name: str, model_cls: Type[ModelT]):
        from google.cloud import firestore  # deferred import — only required if actually used

        self.model_cls = model_cls
        self._client = firestore.Client(project=config.GCP_PROJECT_ID or None)
        self._collection = self._client.collection(collection_name)

    def add(self, item: ModelT) -> None:
        item_id = getattr(item, "id", None)
        if item_id is None:
            raise ValueError(f"{self.model_cls.__name__} has no 'id' field to key on")
        self._collection.document(item_id).set(item.model_dump(mode="json"))

    def get(self, item_id: str) -> Optional[ModelT]:
        doc = self._collection.document(item_id).get()
        return self.model_cls.model_validate(doc.to_dict()) if doc.exists else None

    def list(self) -> Iterable[ModelT]:
        return [self.model_cls.model_validate(doc.to_dict()) for doc in self._collection.stream()]

    def upsert(self, item: ModelT) -> None:
        self.add(item)
