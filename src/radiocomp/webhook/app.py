"""
FastAPI app for the Cloud Run Service that receives Telegram's webhook
calls — one route, plus a health check. Deployed via Dockerfile.webhook,
not the discovery job's Dockerfile (see that file's own comment).

Security: Telegram doesn't sign webhook payloads, but setWebhook accepts a
secret_token which Telegram then echoes back on every real call as the
X-Telegram-Bot-Api-Secret-Token header — checked against
config.TELEGRAM_WEBHOOK_SECRET before anything in the body is trusted.
Without this, --allow-unauthenticated (required so Telegram's own servers
can reach this at all — Telegram can't do GCP IAM auth) would mean anyone
who found the URL could POST fake approve/skip callbacks.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException, Request

from .. import config
from .handlers import handle_callback_query

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
# httpx logs the full request URL at INFO — Telegram's Bot API puts the
# bot token directly in the URL path, so this would otherwise leak the
# token into Cloud Logging on every outbound call (confirmed live,
# 2026-09-04 — the token ended up in real logs this way). Nothing here
# needs per-request HTTP logging; each call site already logs its own
# meaningful line.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = FastAPI()


@app.get("/ping")
def ping() -> dict:
    # Not "/healthz" — that path is intercepted by Google's own front-end
    # infrastructure before it ever reaches this container (confirmed
    # live, 2026-09-04: consistent 404 with no matching log entry on this
    # side, while every other path worked fine) — a known GCP quirk, not a
    # bug in this app. Nothing Telegram-facing depends on this route
    # either way; it's just a manual liveness check.
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    # .strip() on our side: secrets piped from `openssl rand -hex 32 |
    # gcloud secrets create ... --data-file=-` pick up a trailing newline
    # from openssl's own output, which Telegram's registered secret_token
    # never has (Telegram's allowed character set doesn't include one) —
    # confirmed live, 2026-09-04, as a real 403 on every genuine callback.
    expected = config.TELEGRAM_WEBHOOK_SECRET.strip()
    if not expected or x_telegram_bot_api_secret_token != expected:
        raise HTTPException(status_code=403, detail="invalid secret token")

    update = await request.json()
    callback_query = update.get("callback_query")
    if callback_query is not None:
        try:
            handle_callback_query(callback_query)
        except Exception:
            # Always ack Telegram with 200 regardless — an unhandled error
            # here shouldn't make Telegram retry-storm the same update.
            logger.exception("Failed to handle callback_query")

    return {"ok": True}
