"""
Repository interface. Every collection in the data model gets one of
these. There are three implementations (local_json.py, firestore_store.py,
gcs_json.py) — which one you get back from get_repository() is decided
purely by config.STORAGE_BACKEND, so calling code never branches on
backend. gcs_json.py exists specifically for Cloud Run Jobs, which can't
use firestore_store.py here — see that file's docstring for why.
"""

from __future__ import annotations

from typing import Generic, Iterable, Optional, Protocol, Type, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class Repository(Protocol, Generic[ModelT]):
    def add(self, item: ModelT) -> None:
        ...

    def get(self, item_id: str) -> Optional[ModelT]:
        ...

    def list(self) -> Iterable[ModelT]:
        ...

    def upsert(self, item: ModelT) -> None:
        ...

    def delete(self, item_id: str) -> bool:
        """True if `item_id` existed and was removed, False if there was
        nothing to remove (never raises for a missing id). Added 2026-10-07
        after a real gap: a stale FAILED EntryRecord blocks its channel from
        ever being retried (eligibility.py treats *any* existing record as
        "already attempted"), and with no delete() at all the only way to
        clear one was hand-editing the production JSON blob. Nothing in the
        normal discovery/entry-execution flow calls this — it exists for
        deliberate operator tools only (see reset_failed_entry.py), which
        carry their own guard against deleting anything that records a real
        action having happened."""
        ...


def get_repository(collection_name: str, model_cls: Type[ModelT]) -> Repository[ModelT]:
    from .. import config

    if config.STORAGE_BACKEND == "firestore":
        from .firestore_store import FirestoreRepository

        return FirestoreRepository(collection_name, model_cls)
    elif config.STORAGE_BACKEND == "gcs":
        from .gcs_json import GcsJsonRepository

        return GcsJsonRepository(collection_name, model_cls)
    else:
        from .local_json import LocalJsonRepository

        return LocalJsonRepository(collection_name, model_cls)
