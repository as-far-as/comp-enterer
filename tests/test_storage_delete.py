"""
Repository.delete() across all three backends (added 2026-10-07 — see
storage/base.py's docstring and reset_failed_entry.py for why it exists).

LocalJsonRepository is exercised for real against a tmp dir. The GCS and
Firestore backends can't be exercised without real GCP (and this project's
convention is that live storage is verified live, not in unit tests — see
docs/build-log.md), so they're driven through small in-memory fakes of just
the client surface each one touches. That proves the delete() logic itself
(missing id -> False and no write; present id -> removed and persisted,
siblings untouched), not Google's SDK.
"""

from __future__ import annotations

import json

import pytest

from radiocomp import config
from radiocomp.models import EntryChannelType, EntryRecord, EntryStatus
from radiocomp.storage.firestore_store import FirestoreRepository
from radiocomp.storage.gcs_json import GcsJsonRepository
from radiocomp.storage.local_json import LocalJsonRepository


def _record(promotion_id: str = "p1") -> EntryRecord:
    return EntryRecord(promotion_id=promotion_id, channel_type=EntryChannelType.WEB_FORM, status=EntryStatus.FAILED)


# --- local (real) ----------------------------------------------------------


def test_local_delete_removes_only_the_named_record(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    repo = LocalJsonRepository("entry_records", EntryRecord)
    keep, drop = _record("keep"), _record("drop")
    repo.add(keep)
    repo.add(drop)

    assert repo.delete(drop.id) is True

    remaining = {r.id for r in repo.list()}
    assert remaining == {keep.id}
    assert repo.get(drop.id) is None


def test_local_delete_missing_id_returns_false_and_changes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    repo = LocalJsonRepository("entry_records", EntryRecord)
    only = _record()
    repo.add(only)

    assert repo.delete("does-not-exist") is False

    assert [r.id for r in repo.list()] == [only.id]


def test_local_delete_persists_across_a_fresh_repository_instance(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    first = LocalJsonRepository("entry_records", EntryRecord)
    rec = _record()
    first.add(rec)
    first.delete(rec.id)

    second = LocalJsonRepository("entry_records", EntryRecord)
    assert list(second.list()) == []


# --- GCS (faked client) ----------------------------------------------------


class _FakeBlob:
    def __init__(self, store: dict, name: str):
        self._store = store
        self._name = name

    def exists(self) -> bool:
        return self._name in self._store

    def download_as_text(self) -> str:
        return self._store[self._name]

    def upload_from_string(self, payload: str, content_type: str = "") -> None:
        self._store[self._name] = payload


class _FakeBucket:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.upload_count = 0

    def blob(self, name: str) -> _FakeBlob:
        bucket = self

        class _CountingBlob(_FakeBlob):
            def upload_from_string(self, payload: str, content_type: str = "") -> None:
                bucket.upload_count += 1
                super().upload_from_string(payload, content_type)

        return _CountingBlob(self.store, name)


def _gcs_repo(bucket: _FakeBucket) -> GcsJsonRepository:
    repo = GcsJsonRepository.__new__(GcsJsonRepository)  # skip __init__: it builds a real storage.Client
    repo.model_cls = EntryRecord
    repo._blob_name = "entry_records.json"
    repo._bucket = bucket
    return repo


def test_gcs_delete_removes_only_the_named_record_and_persists_it():
    bucket = _FakeBucket()
    repo = _gcs_repo(bucket)
    keep, drop = _record("keep"), _record("drop")
    repo.add(keep)
    repo.add(drop)

    assert repo.delete(drop.id) is True

    persisted = json.loads(bucket.store["entry_records.json"])
    assert set(persisted) == {keep.id}


def test_gcs_delete_missing_id_returns_false_without_writing():
    bucket = _FakeBucket()
    repo = _gcs_repo(bucket)
    repo.add(_record())
    writes_before = bucket.upload_count

    assert repo.delete("does-not-exist") is False

    assert bucket.upload_count == writes_before  # no pointless rewrite of the whole blob


def test_gcs_delete_on_a_collection_that_does_not_exist_yet_returns_false():
    repo = _gcs_repo(_FakeBucket())

    assert repo.delete("anything") is False


# --- Firestore (faked client) ----------------------------------------------


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, docs: dict, doc_id: str):
        self._docs = docs
        self._id = doc_id
        self.delete_calls = 0

    def get(self):
        return _FakeSnapshot(self._docs.get(self._id))

    def set(self, data):
        self._docs[self._id] = data

    def delete(self):
        self.delete_calls += 1
        self._docs.pop(self._id, None)


class _FakeCollection:
    def __init__(self):
        self.docs: dict = {}
        self.refs: list[_FakeDocRef] = []

    def document(self, doc_id: str) -> _FakeDocRef:
        ref = _FakeDocRef(self.docs, doc_id)
        self.refs.append(ref)
        return ref


def _firestore_repo(collection: _FakeCollection) -> FirestoreRepository:
    repo = FirestoreRepository.__new__(FirestoreRepository)  # skip __init__: it builds a real firestore.Client
    repo.model_cls = EntryRecord
    repo._collection = collection
    return repo


def test_firestore_delete_removes_the_named_record_only():
    collection = _FakeCollection()
    repo = _firestore_repo(collection)
    keep, drop = _record("keep"), _record("drop")
    repo.add(keep)
    repo.add(drop)

    assert repo.delete(drop.id) is True

    assert set(collection.docs) == {keep.id}


def test_firestore_delete_missing_id_returns_false_and_never_calls_delete():
    collection = _FakeCollection()
    repo = _firestore_repo(collection)
    repo.add(_record())

    assert repo.delete("does-not-exist") is False

    assert all(ref.delete_calls == 0 for ref in collection.refs)


@pytest.mark.parametrize("make_repo", [lambda: _gcs_repo(_FakeBucket()), lambda: _firestore_repo(_FakeCollection())])
def test_deleted_record_cannot_be_fetched_back(make_repo):
    repo = make_repo()
    rec = _record()
    repo.add(rec)
    assert repo.get(rec.id) is not None

    repo.delete(rec.id)

    assert repo.get(rec.id) is None
