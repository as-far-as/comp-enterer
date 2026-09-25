"""
Where draft/submission screenshots live — the same GCS bucket every other
GCS-backed collection uses (a dedicated `entry_screenshots/` prefix, not a
new bucket), or local `data/entry_screenshots/` for local dev. Returns a
reference string stored on EntryRecord; load_screenshot_bytes() resolves
it back to bytes for Telegram delivery.
"""

from __future__ import annotations

from .. import config

_PREFIX = "entry_screenshots"


def save_screenshot(local_path: str, entry_id: str, stage: str) -> str:
    """stage: 'draft' | 'submitted' | 'submit_failed'. Returns the
    reference to store on EntryRecord.{draft,submitted}_screenshot_path."""
    ref = f"{_PREFIX}/{entry_id}_{stage}.png"

    if config.STORAGE_BACKEND == "gcs":
        from google.cloud import storage

        client = storage.Client(project=config.GCP_PROJECT_ID or None)
        blob = client.bucket(config.GCS_BUCKET_NAME).blob(ref)
        blob.upload_from_filename(local_path, content_type="image/png")
    else:
        import shutil

        dest = config.LOCAL_DATA_DIR / ref
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, dest)

    return ref


def load_screenshot_bytes(ref: str) -> bytes:
    if config.STORAGE_BACKEND == "gcs":
        from google.cloud import storage

        client = storage.Client(project=config.GCP_PROJECT_ID or None)
        blob = client.bucket(config.GCS_BUCKET_NAME).blob(ref)
        return blob.download_as_bytes()
    else:
        return (config.LOCAL_DATA_DIR / ref).read_bytes()
