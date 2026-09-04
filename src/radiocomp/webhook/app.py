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
logger = logging.getLogger(__name__)

app = FastAPI()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if not config.TELEGRAM_WEBHOOK_SECRET or x_telegram_bot_api_secret_token != config.TELEGRAM_WEBHOOK_SECRET:
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
