"""
Shared, small third-party-embed helper — not talkSPORT-specific, since any
future station adapter could hit the same "prose + embedded Google Form,
no 'How to Enter' heading at all" page template (mirrors browser.py's
dismiss_consent_banner() precedent: a tiny, generic helper for a pattern
that isn't owned by any one station).

Confirmed live (2026-09-30) against the two real talkSPORT competition
pages this was built against:
  https://talksport.com/competitions/4598002/win-a-trip-to-philadelphia-for-two/
  https://talksport.com/competitions/4600943/1kwhiteandjordan/
Both embed a real Google Form via
  <iframe class="authenticated-iframe" loading="lazy"
          src="https://docs.google.com/forms/d/e/.../viewform?usp=publish-editor" ...>
present verbatim in the page's own plain static HTML (a plain `httpx` GET
sees it — no Playwright/JS-rendering needed here).

Query-string normalisation: checked live, not assumed. Fetching the same
form both with and without `?usp=publish-editor` returns 200 either way,
with no redirect and materially the same form content — so the query
string is harmless noise, not something that needs stripping. This helper
keeps it as found.
"""

from __future__ import annotations

import re
from typing import Optional

_GOOGLE_FORM_IFRAME_RE = re.compile(r'<iframe[^>]+src="(https://docs\.google\.com/forms/[^"]+)"')


def find_embedded_form_url(html: str) -> Optional[str]:
    """First embedded Google Form `src` found in raw HTML, or None."""
    match = _GOOGLE_FORM_IFRAME_RE.search(html)
    return match.group(1) if match else None
