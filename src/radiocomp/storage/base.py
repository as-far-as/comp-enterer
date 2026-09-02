"""
Repository interface. Every collection in the data model gets one of
these. There are two implementations (local_json.py and firestore.py) —
which one you get back from get_repository() is decided purely by
config.STORAGE_BACKEND, so calling code never branches on backend.
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


def get_repository(collection_name: str, model_cls: Type[ModelT]) -> Repository[ModelT]:
    from .. import config

    if config.STORAGE_BACKEND == "firestore":
        from .firestore_store import FirestoreRepository

        return FirestoreRepository(collection_name, model_cls)
    else:
        from .local_json import LocalJsonRepository

        return LocalJsonRepository(collection_name, model_cls)
