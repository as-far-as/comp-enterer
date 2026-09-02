"""
Firestore-backed repository. Not wired up or tested yet — deliberately —
this file exists so the shape is ready the moment your GCP project does
too, but there was nothing to actually run it against yet.

To activate once you have a project:
  1. pip install google-cloud-firestore (uncomment it in requirements.txt)
  2. set GCP_PROJECT_ID and STORAGE_BACKEND=firestore in your .env
  3. credentials — two options, and this project uses the first because
     Adán runs a dual-Google-account setup across VS Code windows/terminals
     and the app's identity shouldn't depend on whichever personal account
     happens to be logged into gcloud at the time:
       a. set GOOGLE_APPLICATION_CREDENTIALS in .env to the path of a
          dedicated service account key (see README's GCP setup section) —
          google-cloud-firestore picks this env var up automatically before
          falling back to ADC, no code changes needed.
       b. or, without that set, `gcloud auth application-default login`
          (local dev) — ties the app to whichever account ran that command.
     Inside a Cloud Run Job/Service, the runtime service account is used
     either way and this whole question doesn't come up.

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
