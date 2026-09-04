"""
Thin wrapper around the three Telegram Bot API methods this project
actually needs — not the python-telegram-bot library, deliberately: that
library's real value is its update-handling/webhook machinery, which
FastAPI already gives webhook/app.py directly. Three plain REST calls
don't need a framework on top.

Every call is plain JSON over httpx — no `parse_mode` anywhere, ever.
Scraped competition titles/prize text routinely contain characters
MarkdownV2 requires escaping (". ! ( ) -" and more); sending them
unescaped just 400s. Plain text throughout is a deliberate, permanent
choice, not a gap to "improve" later.
"""

from __future__ import annotations

from typing import Optional

import httpx

from .. import config

_API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _call(method: str, payload: dict) -> dict:
    url = _API_BASE.format(token=config.TELEGRAM_BOT_TOKEN, method=method)
    resp = httpx.post(url, json=payload, timeout=config.REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API {method} failed: {data}")
    return data["result"]


def send_message(chat_id: str, text: str, reply_markup: Optional[dict] = None) -> dict:
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return _call("sendMessage", payload)


def answer_callback_query(callback_query_id: str, text: Optional[str] = None) -> dict:
    payload: dict = {"callback_query_id": callback_query_id}
    if text is not None:
        payload["text"] = text
    return _call("answerCallbackQuery", payload)


def edit_message_text(chat_id, message_id: int, text: str, reply_markup: Optional[dict] = None) -> dict:
    payload: dict = {"chat_id": chat_id, "message_id": message_id, "text": text}
    # Explicit even when empty: editMessageText leaves the *existing*
    # keyboard in place if reply_markup is omitted entirely — it does not
    # clear it. Always pass this, even as {"inline_keyboard": []}.
    payload["reply_markup"] = reply_markup if reply_markup is not None else {"inline_keyboard": []}
    return _call("editMessageText", payload)
