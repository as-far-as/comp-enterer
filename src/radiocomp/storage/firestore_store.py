"""
Firestore-backed repository. Not wired up or tested yet — deliberately —
this file exists so the shape is ready the moment your GCP project does
too, but there was nothing to actually run it against yet.

To activate once you have a project:
  1. pip install google-cloud-firestore (uncomment it in requirements.txt)
  2. set GCP_PROJECT_ID and STORAGE_BACKEND=firestore in your .env
  3. credentials: `gcloud auth application-default login` (local dev) —
     google-cloud-firestore picks up ADC automatically. A dedicated service
     account key (via GOOGLE_APPLICATION_CREDENTIALS, checked before ADC)
     was the original plan, to keep the app's identity independent of
     whichever personal account is logged into gcloud/VS Code — but this
     project's GCP org enforces a Deny policy blocking all service-account
     Firestore access regardless of IAM role, so that's not available here.
     See README's GCP setup section and docs/build-log.md (2026-09-02) for
     the full trail, in case a future account/org setup allows revisiting
     it. Inside a Cloud Run Job/Service, the runtime service account is used
     regardless — worth re-checking against this same restriction first.

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
