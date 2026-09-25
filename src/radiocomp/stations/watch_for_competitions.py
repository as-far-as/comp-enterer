"""
A lightweight "has a competition page appeared?" watcher for stations
that don't have a real, live example to build a proper classifying
adapter against yet (see seed_southeast_london.py's docstring for why).

Deliberately NOT a full adapter — no Promotion/EntryChannel records, no
classification of free/paid, no channel extraction. Just answers one
question per station, per run: does a "Win"/"Competitions"/"Prize" link
exist on the homepage that wasn't there last time? If so, send a plain
Telegram nudge so a human can look and, if it's real, a proper adapter
can then be built against that real example — matching this project's
established "test against real captured data, never speculative parsing
logic" convention, just applied to the discovery step itself rather than
to a classifier.

Persistence is a tiny flat {station_name: last_seen_url} JSON blob (same
per-backend branching as storage/user_profile_store.py, adapted for a
dict instead of a single Pydantic model) — not a Repository, since there's
no natural per-station "id" collection here, just one small shared state
file.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .. import config
from ..models import Station
from ..notify import telegram_client

logger = logging.getLogger(__name__)

_BLOB_NAME = "watched_competition_links.json"
_LINK_TEXT_RE = re.compile(r"\b(win|competition|competitions|prize|prizes)\b", re.IGNORECASE)


def _load_seen() -> dict[str, str]:
    if config.STORAGE_BACKEND == "gcs":
        from google.cloud import storage

        client = storage.Client(project=config.GCP_PROJECT_ID or None)
        blob = client.bucket(config.GCS_BUCKET_NAME).blob(_BLOB_NAME)
        if not blob.exists():
            return {}
        return json.loads(blob.download_as_text())
    elif config.STORAGE_BACKEND == "firestore":
        from google.cloud import firestore

        client = firestore.Client(project=config.GCP_PROJECT_ID or None)
        doc = client.collection("watch_state").document("competition_links").get()
        return doc.to_dict() or {} if doc.exists else {}
    else:
        path = config.LOCAL_DATA_DIR / _BLOB_NAME
        if not path.exists():
            return {}
        return json.loads(path.read_text())


def _save_seen(seen: dict[str, str]) -> None:
    if config.STORAGE_BACKEND == "gcs":
        from google.cloud import storage

        client = storage.Client(project=config.GCP_PROJECT_ID or None)
        blob = client.bucket(config.GCS_BUCKET_NAME).blob(_BLOB_NAME)
        blob.upload_from_string(json.dumps(seen, indent=2), content_type="application/json")
    elif config.STORAGE_BACKEND == "firestore":
        from google.cloud import firestore

        client = firestore.Client(project=config.GCP_PROJECT_ID or None)
        client.collection("watch_state").document("competition_links").set(seen)
    else:
        path = config.LOCAL_DATA_DIR / _BLOB_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seen, indent=2))


def check_for_competition_link(homepage_url: str) -> Optional[str]:
    """None if no competition-looking nav/footer link is found (including
    on a fetch failure — logged, not raised, same "a quiet station isn't
    an error" posture as every adapter's own fetch handling). Detection
    only: never fetches or classifies the linked page itself, since
    that's exactly the part with no real example to build a classifier
    against yet."""
    try:
        resp = httpx.get(
            homepage_url,
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch %s: %s", homepage_url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True)
        if text and _LINK_TEXT_RE.search(text):
            return urljoin(homepage_url, link["href"])
    return None


def watch_for_new_competitions(stations: list[Station]) -> list[tuple[Station, str]]:
    """Returns only newly-appeared (station, url) pairs — a link already
    flagged on a previous run doesn't fire again, so this is safe to call
    on every scheduled discovery pass without ever spamming."""
    seen = _load_seen()
    newly_found: list[tuple[Station, str]] = []

    for station in stations:
        if not station.base_urls:
            continue
        link = check_for_competition_link(station.base_urls[0])
        if link is None:
            continue
        if seen.get(station.name) == link:
            continue
        newly_found.append((station, link))
        seen[station.name] = link

    if newly_found:
        _save_seen(seen)

    return newly_found


def _notify(station: Station, url: str) -> None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    text = (
        f"👀 Possible new competition on {station.name}\n"
        f"{url}\n\n"
        f"Worth checking manually — no automated classification yet for this station."
    )
    telegram_client.send_message(config.TELEGRAM_CHAT_ID, text)


def run(stations: list[Station]) -> int:
    """The entrypoint run_discovery.py calls. Returns how many new links
    were found and notified, for logging. Always logs a summary line
    (matching every adapter's own "X listed, Y new" convention) even when
    nothing new is found — a silent step is indistinguishable from a
    silently-swallowed failure otherwise."""
    newly_found = watch_for_new_competitions(stations)
    for station, url in newly_found:
        _notify(station, url)
        logger.info("New competition-looking link on %s: %s", station.name, url)
    logger.info(
        "Competition watcher: checked %d station(s), %d new link(s) found",
        len(stations),
        len(newly_found),
    )
    return len(newly_found)
