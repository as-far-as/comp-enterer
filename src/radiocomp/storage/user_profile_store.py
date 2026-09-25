"""
UserProfile storage — deliberately outside the Repository/get_repository()
pattern every other model uses. UserProfile has no `id` field on purpose
(see its own docstring: "deliberately singular... no concept of a second
identity"), and every Repository implementation keys everything by
`item.id`, raising if it's missing. Rather than bolt an id onto the one
model that's explicitly not meant to be a keyed collection, this is a
single JSON object, not an id-keyed dict — one object per storage backend,
mirroring config.STORAGE_BACKEND the same way get_repository() does.

Written for setup_user_profile.py to call directly. Nothing else in this
codebase should construct a UserProfile from anywhere except what this
module loads — the whole point of "single real identity only" is that
there's exactly one source of truth for who's entering.
"""

from __future__ import annotations

import json
from typing import Optional

from .. import config
from ..models import UserProfile

_BLOB_NAME = "user_profile.json"


def load_user_profile() -> Optional[UserProfile]:
    if config.STORAGE_BACKEND == "gcs":
        from google.cloud import storage

        client = storage.Client(project=config.GCP_PROJECT_ID or None)
        blob = client.bucket(config.GCS_BUCKET_NAME).blob(_BLOB_NAME)
        if not blob.exists():
            return None
        raw = json.loads(blob.download_as_text())
    elif config.STORAGE_BACKEND == "firestore":
        from google.cloud import firestore

        client = firestore.Client(project=config.GCP_PROJECT_ID or None)
        doc = client.collection("user_profile").document("profile").get()
        if not doc.exists:
            return None
        raw = doc.to_dict()
    else:
        path = config.LOCAL_DATA_DIR / _BLOB_NAME
        if not path.exists():
            return None
        raw = json.loads(path.read_text())

    return UserProfile.model_validate(raw)


def save_user_profile(profile: UserProfile) -> None:
    raw = json.loads(profile.model_dump_json())

    if config.STORAGE_BACKEND == "gcs":
        from google.cloud import storage

        client = storage.Client(project=config.GCP_PROJECT_ID or None)
        blob = client.bucket(config.GCS_BUCKET_NAME).blob(_BLOB_NAME)
        blob.upload_from_string(json.dumps(raw, indent=2, default=str), content_type="application/json")
    elif config.STORAGE_BACKEND == "firestore":
        from google.cloud import firestore

        client = firestore.Client(project=config.GCP_PROJECT_ID or None)
        client.collection("user_profile").document("profile").set(raw)
    else:
        path = config.LOCAL_DATA_DIR / _BLOB_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, indent=2, default=str))
