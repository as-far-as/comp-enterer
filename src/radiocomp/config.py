"""
Central config. Reads from environment variables (via .env in local dev),
with sensible local-first defaults so the rest of the codebase never has to
know whether it's talking to a local JSON store or real Firestore.

Once your GCP project exists:
  - set GCP_PROJECT_ID to your project id
  - set STORAGE_BACKEND=firestore for local dev — `gcloud auth application-
    default login` locally (google-cloud-firestore picks up ADC
    automatically). A dedicated service account key isn't an option on this
    project's account/org: an org-level Deny policy blocks all service-
    account Firestore access here regardless of role, confirmed by actually
    running a real Cloud Run Job against Firestore and watching it get
    denied the same way a local test with a custom service account did
    (see docs/build-log.md, 2026-09-02 and 2026-09-03).
  - set STORAGE_BACKEND=gcs (and GCS_BUCKET_NAME) for anything that runs as
    a Cloud Run Job/Service — Cloud Run's runtime service account can't
    reach Firestore for the reason above, but the identical check against
    Cloud Storage worked fine, so that's what gcs_json.py uses instead.

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

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")  # "local" | "firestore" | "gcs"
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_REGION = os.environ.get("GCP_REGION", "europe-west2")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "")  # only used when STORAGE_BACKEND=gcs

# Telegram bot — notify/ (outbound) and webhook/ (receives Approve/Skip
# taps). TELEGRAM_WEBHOOK_SECRET is only read by webhook/app.py; it's not a
# third-party credential, just random bytes you mint yourself for verifying
# incoming requests actually came from Telegram (see webhook/app.py). All
# three are optional — notify/send.py no-ops if the first two are unset.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

# Polite crawling defaults — see aggregators/loquax.py for why this matters.
USER_AGENT = os.environ.get(
    "RADIOCOMP_USER_AGENT",
    "radiocomp-personal-bot/0.1 (+personal research project, single user, "
    "contact via GitHub profile if this is a problem)",
)
REQUEST_TIMEOUT_SECONDS = 20
