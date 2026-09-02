"""
Central config. Reads from environment variables (via .env in local dev),
with sensible local-first defaults so the rest of the codebase never has to
know whether it's talking to a local JSON store or real Firestore.

Once your GCP project exists:
  - set GCP_PROJECT_ID to your project id
  - set STORAGE_BACKEND=firestore
  - credentials: `gcloud auth application-default login` locally (google-cloud-
    firestore picks up ADC automatically), or set GOOGLE_APPLICATION_CREDENTIALS
    to a dedicated service account key if your account/org supports one — this
    project's doesn't (an org-level Deny policy blocks all service-account
    Firestore access here regardless of role; see README's GCP setup section
    and docs/build-log.md, 2026-09-02, for the full diagnostic trail). Inside
    a Cloud Run Job/Service, the runtime service account is used regardless —
    worth re-checking against this same restriction before relying on it.

Until then, STORAGE_BACKEND defaults to "local" and everything is written
to ./data/*.json, so you can build and test the whole discovery pipeline
today without touching GCP at all.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_DATA_DIR = PROJECT_ROOT / "data"

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")  # "local" | "firestore"
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_REGION = os.environ.get("GCP_REGION", "europe-west2")

# Polite crawling defaults — see aggregators/loquax.py for why this matters.
USER_AGENT = os.environ.get(
    "RADIOCOMP_USER_AGENT",
    "radiocomp-personal-bot/0.1 (+personal research project, single user, "
    "contact via GitHub profile if this is a problem)",
)
REQUEST_TIMEOUT_SECONDS = 20
