"""
Global WIN — Global's own first-party shared competition platform,
network-wide across Global's entire portfolio (Heart, Capital, Classic
FM, Gold, LBC, Radio X, Smooth, Capital Xtra, Big Top 40, Global Player,
Riviera Radio, and "Win Plus"/Global WIN's own brand entry), served
per-brand at `winplus.<brand>.co.uk`/`.com` (e.g. `winplus.heart.co.uk`,
`winplus.capitalfm.com` — every brand instance is the same shared
backend, confirmed live 2026-09-25, see the "Generalised" note below).
`station_name_raw=STATION_NAME` ("Global WIN"), `network=STATION_NETWORK`
("Global") — both need to be members of `compliance/engine.py`'s
`SHARED_LIMIT_NETWORKS["Global"]`, same self-registration pattern
`bauer_makemeawinner.py`'s own `station_name_raw` uses for
`SHARED_LIMIT_NETWORKS["Bauer"]`.

**Generalised from a Heart-only adapter to a whole-platform one
(2026-09-25).** Originally `heart_global.py` monitored only Heart's own
numeric brand id (2) inside the shared `brands` array on
`/data/competitions/list.json`, filtering out every competition not
tagged with it. Re-confirmed live that `/data/init.json`'s full `brands`
map is entirely Global's own portfolio — nothing external mixed in (see
history below) — and that competitions are brand-scoped for *display*
only (a real competition, id 13771, "Win Two Tickets to See Manic Street
Preachers and Suede", carries `brands: [67, 6]` — Global Player + Radio X
only, no Heart at all) but not for the underlying entry mechanics: same
API, same fields, same T&Cs template regardless of which brand(s) show
it. Filtering to one brand meant the exact same shared competition would
otherwise be recorded as N near-duplicate `Promotion` rows if this module
were ever pointed at more than one brand — the same near-duplicate-row
problem `bauer_makemeawinner.py` already solved by modelling itself as
one shared `station_name_raw` rather than per-station. So this module now
processes **every** non-hidden competition in `list.json` exactly once,
regardless of brand tagging, instead of filtering to Heart's brand id.
`fetch_brand_id()`/`/data/init.json` are still fetched, but purely for an
informational sanity-check log line now — no longer used to gate which
competitions get recorded. Renamed `heart_global.py` -> `global_win.py`
and `STATION_NAME` from `"Heart"` to `"Global WIN"` (the platform's own
real branding — confirmed live in `init.json`'s own `"winplus"` brand
entry, `"brandName": "Win Plus"`) accordingly. See docs/build-log.md's
2026-09-25 entry for the live-verification numbers.

**A materially different, and better, outcome than the plan this module
was originally scoped from assumed.** The plan's Part 2 (see
docs/build-log.md, 2026-09-09) dropped Heart entirely after finding that
one of Heart's off-page entry subdomains (`comp.heart.co.uk`) showed a
misleading "successfully entered" state when read anonymously, and
assumed reaching real, trustworthy free/paid status required a genuine
personal Gigya-SSO login. A later, deeper investigation found the
platform that actually matters for discovery is a *different* one —
`winplus.heart.co.uk` — and re-confirmed live here (2026-09-23) that a
real competition page there, fetched with **no login attempted at any
point**, plainly shows both `"FREE ENTRY: No purchase necessary."` and
`"Paid entry from £X..."` text on the very same page (confirmed via
Playwright across 5 real live competitions: `/competition/13201/
win-pound10000`, `/competition/13270/win-a-ninja-double-stack-air-fryer`,
`/competition/13635/cash-call`, `/competition/13102/
win-a-pound500-heartwood-gift-voucher`, `/competition/13399/
win-a-pound250-supermarket-voucher` — network-request capture during each
load showed only routine analytics/consent/Stripe-config calls, nothing
resembling a real submission, same "verify properly rather than assume"
check as the original `comp.heart.co.uk` incident). Sign-in is needed to
actually *submit* an entry ("Step 1 — Sign in with your global iD..." is
shown on the page), never to *read* its free/paid status. So, unlike the
plan's Part 2, **this adapter's discovery/`ingest()` needs no credentials
and no login at all** — same posture as every other adapter in this
codebase.

**A second, bigger surprise, found by not stopping at the first
confirmation**: `winplus.heart.co.uk` itself is a pure client-rendered
Vue SPA — a plain `httpx` GET of either the homepage or any competition
page returns only an empty `id="app"` shell (confirmed live, 2026-09-23),
so reading the rendered page for real would need Playwright, same as the
talkSPORT widget. But Playwright's own network-request log (captured
during the same safe, no-login page loads above) showed the real
rendered content comes from a clean, **unauthenticated-by-design JSON
API** served from the same origin:
  - `GET /data/init.json` — site config, including a `brands` map of
    brand code → numeric id (`"heart": {"id": 2, ...}`).
  - `GET /data/competitions/list.json` — every competition currently in
    the system, each with a `brands` array of the numeric ids it's shown
    on (Heart's homepage only ever shows the ones whose `brands` array
    contains `2` — confirmed by diffing the 10 real links Heart's
    homepage actually rendered against this list's `brands` fields, which
    matched exactly) and a genuine `competitionEntryType` field —
    `"free"` or `"paid"`, straight from Global's own backend.
  - `GET /data/competitions/{id}/details.json` — full detail for one
    competition: `title`, `dateStop`, `competitionEntryType` again, and
    `meta.termsAndConditions` (real HTML T&Cs body, same shape as
    `bauer_makemeawinner.py`'s `campaign/info` body).
This is the same kind of discovery as `bauer_makemeawinner.py`'s
`api.winhappy.com` (found via Playwright network capture, then confirmed
to work through plain `httpx` alone) — **no Playwright needed for this
adapter at all**, and a second first for this codebase alongside Bauer's:
`competitionEntryType` is a real field from the source system, not a
regex/keyword guess against scraped text, so it's confidently classified
in both directions (`is_free_route=True` *or* `False`), never guessed.
The brand id (`2` for "heart") is resolved live from `init.json` every
run rather than hardcoded, on the same "never guess a value, even one
that's unlikely to change" posture as everything else in this codebase.

Real data at capture time (2026-09-23): 10 live competitions shown on
Heart's homepage, 2 of them (`win-two-tickets-to-see-westlife`,
`win-two-tickets-to-see-titanique-the-musical`) confidently `free`, the
rest confidently `paid`. Every real `paid` competition has exactly one
genuine free "no purchase necessary" alternative described only in its
own `meta.termsAndConditions` body — never both, and never neither — an
identical pattern to `bauer_makemeawinner.py`'s own real gap (a paid
`WEB_FORM` campaign with a free phone/post alternative the summary
listing never mentions): of the real paid competitions seen, two
(id 13201 "Win £10,000" and id 13635 "Cash Call") use a free **phone**
route, every other real paid competition instead uses a free **postal**
route to the same real PO Box (`PO Box 8669, Derby, DE1 9SR`), and the
confidently-`free` competitions have neither (already free online, no
alternative route needed). **Tracked for visibility only, per CLAUDE.md — a phone channel
is never auto-dialled, full stop, regardless of how it's classified**;
the real T&Cs text itself makes the same point independently ("We
reserve the right to withhold any prize from you if we believe that you
are using automated dialling technology...").

**Gigya login — `login()`, deliberately not called anywhere in
`ingest()`.** The user has separately signed off on setting up real
personal Global Player credential handling now, for *future*
entry-submission work only, accepting the real risk that a genuine
Global Player account could be suspended if Global's own anti-automation
detection ever flags it — see docs/build-log.md. Confirmed live
(2026-09-23, passively — reading Global's own already-loaded JS and
network requests during the same no-login page loads above, never an
actual login attempt): Global Player's public Gigya `apiKey`
(`3_wJvsL2DHpyMc11IB8pI8CpCqp720k-9M1ZNbnnTfItUtg_NzEhvASdN-uO1GNzhp`)
appears verbatim as the `APIKey`/`sourceKey` on real `cdns.eu1.gigya.com/
js/sso.htm` and `sdk.config.get` requests the page itself makes — a
public, client-side-by-design value, not a secret, same convention as
every Gigya integration. The real login call is Gigya's own standard
REST endpoint, `POST https://accounts.eu1.gigya.com/accounts.login`,
with `apiKey`, `loginID` (the account email), `password`,
`sessionExpiration=0` (session-only — a fresh login every run, nothing
persisted, matching Bauer's own guest-token pattern of "fresh per-run,
nothing written to disk"), and `format=json`. A successful response
carries Gigya's standard `UID`, `UIDSignature`, `signatureTimestamp`
fields (well-documented, not proprietary to Global); an unsuccessful one
carries a non-zero `errorCode`. Global's own JS then derives an
app-specific bearer token from those three fields —
`base64(json.dumps({"gigyaUID": UID, "timestamp": signatureTimestamp,
"signature": UIDSignature}))` — sent as `Authorization: Gigya <token>` on
later calls to Global's own backend (`bff-web-guacamole.musicradio.com`).
`login()` implements exactly this: makes the real request, derives and
returns that token, held in memory by the caller for that run only (same
as Bauer's `bearer: str`) — never persisted to any repository, GCS
bucket, or local file. It was **never actually exercised against the
live site while building this** (no real `GLOBAL_PLAYER_EMAIL`/
`GLOBAL_PLAYER_PASSWORD` exist in this environment, and this codebase
must never invent or ask for real credentials) — that's a real gap this
module ships with, to be closed later by the user themselves, once
they've created the real secrets. If either env var is unset, `login()`
raises `RuntimeError` immediately rather than attempting a call with
empty credentials.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import date, datetime
from typing import Optional

import httpx

from .. import config
from ..dedup import promotion_dedup_hash
from ..models import DiscoveredVia, EntryChannel, EntryChannelType, Promotion
from ..storage.base import get_repository

logger = logging.getLogger(__name__)

_SITE_BASE = "https://winplus.heart.co.uk"
_INIT_URL = f"{_SITE_BASE}/data/init.json"
_LIST_URL = f"{_SITE_BASE}/data/competitions/list.json"
_DETAIL_URL_TMPL = _SITE_BASE + "/data/competitions/{comp_id}/details.json"
# Used only for fetch_brand_id()'s informational sanity-check log line in
# ingest() now, not for filtering which competitions get recorded — see
# module docstring's "Generalised" note. "heart" specifically because it's
# a well-known, long-lived brand code on this platform, not because it's
# special to this module any more.
_BRAND_CODE = "heart"

STATION_NAME = "Global WIN"
STATION_NETWORK = "Global"

# Public, client-side Gigya API key for Global Player's login flow — read
# verbatim off Global's own already-loaded JS/network requests, not a
# secret (see module docstring). Distinct from the per-site `sourceKey`
# winplus.heart.co.uk itself uses for its own Gigya bootstrap.
_GIGYA_API_KEY = "3_wJvsL2DHpyMc11IB8pI8CpCqp720k-9M1ZNbnnTfItUtg_NzEhvASdN-uO1GNzhp"
_GIGYA_LOGIN_URL = "https://accounts.eu1.gigya.com/accounts.login"

# Title-only, same conservative reasoning as bauer_makemeawinner.py's own
# prize extraction — a body/T&Cs fallback risks picking up an unrelated
# figure (e.g. one of the paid entry-bundle prices, which appear right
# next to the title in the real page's own rendered text).
_PRIZE_RE = re.compile(r"£\s?([\d,]+(?:\.\d+)?)", re.IGNORECASE)

# Confirmed live across every real paid competition that has a phone
# route (2026-09-23): "Free Entry Route by phone call 5.1. To enter the
# Promotion by phone call, you must call 03434150054 (the 'Competition
# Phone Service') from a valid UK mobile phone number... 5.2. Phone calls
# from the UK are charged at your standard network rate only. This is not
# a premium rate phone call." — bounded to the text right after the
# heading (not open-ended) so it can't accidentally match a phone number
# quoted elsewhere in a long T&Cs document.
_PHONE_HEADING_RE = re.compile(r"Free Entry Route by phone call(.{0,600})", re.IGNORECASE | re.DOTALL)
_CALL_NUMBER_RE = re.compile(r"call\s+(0\d[\d ]{8,}\d)", re.IGNORECASE)
_STANDARD_RATE_RE = re.compile(r"standard\s+network\s+rate", re.IGNORECASE)

# Confirmed live across every real paid competition that has a post route
# instead (2026-09-23): "Free Entry via Post 5.1. To enter via post you
# must send your name and a UK mobile telephone number on a postcard or
# on/in an envelope to: GWAIRFRYER PO Box 8669, Derby, DE1 9SR." — the
# campaign-specific prefix before "PO Box" varies (GWAIRFRYER,
# GWHEARTWOOD, GWMACBOOK, ...), the PO Box/postcode itself has been
# identical on every real example seen so far.
_POST_HEADING_RE = re.compile(r"Free Entry via Post(.{0,600})", re.IGNORECASE | re.DOTALL)
_PO_BOX_RE = re.compile(r"(PO Box\s+[\w\- ,]+?[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})", re.IGNORECASE)


def _headers() -> dict:
    return {
        "User-Agent": config.USER_AGENT,
        "Referer": f"{_SITE_BASE}/",
        "Accept": "application/json, text/plain, */*",
    }


def fetch_brand_id(client: httpx.Client, brand_code: str = _BRAND_CODE) -> Optional[int]:
    """None if init.json's brands map doesn't have this brand_code at all
    (site shape changed). No longer used to gate which competitions
    ingest() records (see module docstring) — ingest() only logs this
    informationally now, as a lightweight "does init.json still look like
    the shape we expect" check."""
    resp = client.get(_INIT_URL, headers=_headers(), timeout=config.REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json()
    brand = data.get("brands", {}).get(brand_code)
    return brand.get("id") if brand else None


def fetch_competition_list(client: httpx.Client) -> list[dict]:
    resp = client.get(_LIST_URL, headers=_headers(), timeout=config.REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()


def fetch_competition_details(client: httpx.Client, comp_id: int) -> dict:
    resp = client.get(
        _DETAIL_URL_TMPL.format(comp_id=comp_id), headers=_headers(), timeout=config.REQUEST_TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    return resp.json()


def _tandc_text(detail: dict) -> str:
    """The details.json meta.termsAndConditions field is real HTML
    (paragraphs, bold, &nbsp; entities) — strip tags and normalise the
    entities actually observed live, same approach as
    bauer_makemeawinner.py's own _tandc_text()."""
    body = (detail.get("meta") or {}).get("termsAndConditions") or ""
    text = re.sub(r"<[^<]+?>", " ", body)
    text = text.replace("&nbsp;", " ").replace("&pound;", "£").replace("&rsquo;", "'").replace(
        "&ldquo;", '"'
    ).replace("&rdquo;", '"').replace("&amp;", "&")
    return re.sub(r"\s+", " ", text)


def _parse_deadline(date_stop: Optional[str]) -> Optional[date]:
    if not date_stop:
        return None
    try:
        return datetime.fromisoformat(date_stop.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def extract_phone_channel(tandc_text: str) -> Optional[EntryChannel]:
    """None if this competition has no phone entry route at all — not
    every real paid competition does (confirmed live — most use the post
    route instead, see module docstring), and that's a real absence, not
    a parsing failure worth flagging for review."""
    heading_match = _PHONE_HEADING_RE.search(tandc_text)
    if not heading_match:
        return None
    section = heading_match.group(0)

    number_match = _CALL_NUMBER_RE.search(section)
    is_standard_rate = bool(_STANDARD_RATE_RE.search(section))
    return EntryChannel(
        promotion_id="",
        channel_type=EntryChannelType.PHONE_ENTRY,
        is_free_route=True if is_standard_rate else None,
        cost_to_entrant_gbp=0.0 if is_standard_rate else None,
        channel_url_or_number=number_match.group(1).strip() if number_match else None,
        review_recommended=not is_standard_rate,
        raw_excerpt=section[:400],
    )


def extract_post_channel(tandc_text: str) -> Optional[EntryChannel]:
    """None if this competition has no postal entry route at all."""
    heading_match = _POST_HEADING_RE.search(tandc_text)
    if not heading_match:
        return None
    section = heading_match.group(0)

    address_match = _PO_BOX_RE.search(section)
    return EntryChannel(
        promotion_id="",
        channel_type=EntryChannelType.POST,
        is_free_route=True,
        cost_to_entrant_gbp=0.0,
        channel_url_or_number=address_match.group(1).strip() if address_match else None,
        review_recommended=False,
        raw_excerpt=section[:400],
    )


def parse_detail(detail: dict) -> tuple[Optional[Promotion], list[EntryChannel]]:
    """Pure. Takes one competition's already-fetched details.json body
    (see fetch_competition_details) — unlike wayin.py's parse_detail(),
    this doesn't take raw HTML, because winplus.heart.co.uk's real
    content is this clean JSON API, not its (client-rendered, empty when
    fetched plainly) HTML — see module docstring. (None, []) if the
    response is missing id/slug/title entirely, which would mean this
    isn't a real competition record rather than a parsing gap worth
    guessing around."""
    comp_id = detail.get("id")
    slug = detail.get("slug")
    title = (detail.get("title") or "").strip()
    if not comp_id or not slug or not title:
        return None, []

    source_url = f"{_SITE_BASE}/competition/{comp_id}/{slug}"
    deadline = _parse_deadline(detail.get("dateStop"))

    # A genuine source field, not an inferred/guessed pattern (see
    # models.Promotion.recurrence_series_id) — confirmed live 2026-09-28
    # on "Capital's Bong Game 2026", a real daily round: competitionIsRound
    # is true and competitionScheduleId (11497) is shared identically
    # across every day's own separate competition id/dateStart/dateStop.
    # Lets notify/send.py send one message per series instead of one per
    # daily occurrence.
    schedule_id = detail.get("competitionScheduleId")
    recurrence_series_id = str(schedule_id) if detail.get("competitionIsRound") and schedule_id else None

    prize_match = _PRIZE_RE.search(title)
    prize_value = None
    if prize_match:
        try:
            prize_value = float(prize_match.group(1).replace(",", ""))
        except ValueError:
            prize_value = None

    promo = Promotion(
        station_name_raw=STATION_NAME,
        network=STATION_NETWORK,
        title=title,
        prize_value_gbp=prize_value,
        entry_deadline=deadline,
        discovered_via=DiscoveredVia.DIRECT,
        source_url=source_url,
        dedup_hash=promotion_dedup_hash(STATION_NAME, title, deadline),
        recurrence_series_id=recurrence_series_id,
    )

    # competitionEntryType comes straight from Global's own backend — a
    # genuine field, not a text-classification guess, so (like Bauer's
    # own is_free) this is confidently classified in both directions,
    # never review_recommended unless the field is genuinely absent/
    # unrecognised.
    entry_type = detail.get("competitionEntryType")
    if entry_type == "free":
        is_free: Optional[bool] = True
    elif entry_type == "paid":
        is_free = False
    else:
        is_free = None
    web_form_channel = EntryChannel(
        promotion_id="",
        channel_type=EntryChannelType.WEB_FORM,
        is_free_route=is_free,
        cost_to_entrant_gbp=0.0 if is_free else None,
        channel_url_or_number=source_url,
        review_recommended=is_free is None,
        raw_excerpt=f"winplus.heart.co.uk details.json: competitionEntryType={entry_type!r}",
    )
    channels = [web_form_channel]

    # A paid web_form competition routinely has its own genuinely free
    # "no purchase necessary" alternative (phone XOR post, never both,
    # never neither on the real data seen so far — see module docstring),
    # described only in the T&Cs body, never in the list/summary fields.
    # Tracked for visibility only; never automated.
    tandc_text = _tandc_text(detail)
    phone_channel = extract_phone_channel(tandc_text)
    if phone_channel:
        channels.append(phone_channel)
    post_channel = extract_post_channel(tandc_text)
    if post_channel:
        channels.append(post_channel)

    return promo, channels


def ingest() -> tuple[list[Promotion], list[EntryChannel]]:
    """No credentials touched anywhere in this function — see module
    docstring. Processes every non-hidden competition in
    competitions/list.json exactly once, regardless of which Global
    brand(s) it's tagged with (see module docstring's "Generalised"
    note) — no longer filtered to Heart's brand id. Two real calls per
    run beyond the one details.json per competition: init.json (resolved
    only for an informational log line now, not used to gate anything)
    and competitions/list.json itself (every live competition + which
    brands show it), then one details.json per competition (for
    title/deadline/T&Cs — the list endpoint alone doesn't carry these)."""
    promo_repo = get_repository("promotions", Promotion)
    channel_repo = get_repository("entry_channels", EntryChannel)
    existing_hashes = {p.dedup_hash for p in promo_repo.list()}

    new_promotions: list[Promotion] = []
    new_channels: list[EntryChannel] = []

    with httpx.Client() as client:
        try:
            brand_id = fetch_brand_id(client)
            logger.info(
                "winplus.heart.co.uk init.json resolved %r brand id as %r (informational only — every "
                "non-hidden competition is processed regardless of brand tagging, see module docstring)",
                _BRAND_CODE,
                brand_id,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "Failed to resolve %r brand id from winplus.heart.co.uk init.json (informational only, "
                "continuing with the full unfiltered listing): %s",
                _BRAND_CODE,
                exc,
            )

        try:
            listing = fetch_competition_list(client)
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch Global WIN competition list: %s", exc)
            return new_promotions, new_channels

        items = [item for item in listing if not item.get("hidden")]

        seen_this_run: set[str] = set()
        for item in items:
            comp_id = item.get("id")
            try:
                detail = fetch_competition_details(client, comp_id)
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch details for Global WIN competition %r: %s", comp_id, exc)
                continue

            try:
                promo, channels = parse_detail(detail)
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping malformed Global WIN competition %r: %s", comp_id, exc)
                continue
            if promo is None:
                logger.warning(
                    "Could not extract a promotion from Global WIN competition %r — missing id/slug/title",
                    comp_id,
                )
                continue

            if promo.dedup_hash in seen_this_run or promo.dedup_hash in existing_hashes:
                continue
            seen_this_run.add(promo.dedup_hash)

            promo_repo.add(promo)
            new_promotions.append(promo)
            for channel in channels:
                channel.promotion_id = promo.id
                channel_repo.add(channel)
                new_channels.append(channel)

    logger.info(
        "Global WIN ingestion: %d listed, %d new promotions, %d entry channels recorded",
        len(items),
        len(new_promotions),
        len(new_channels),
    )
    return new_promotions, new_channels


def _derive_bff_token(uid: str, uid_signature: str, signature_timestamp: str) -> str:
    """Pure. Global's own JS derives its backend bearer token this way
    from a successful Gigya accounts.login response — see module
    docstring. Not itself a network call."""
    payload = {"gigyaUID": uid, "timestamp": signature_timestamp, "signature": uid_signature}
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def login(client: httpx.Client) -> str:
    """Real Gigya accounts.login call + token derivation — see module
    docstring for the full mechanics and the explicit accepted-risk
    statement. **Standalone: never called from ingest() or
    run_discovery.py, only ever on-demand, by name, for future
    entry-submission work.** Returns the derived bearer token; the caller
    holds it in memory for that run only — never persisted to any
    repository, GCS blob, or local file, same as Bauer's guest bearer
    token.

    Raises RuntimeError immediately (no network call attempted) if either
    GLOBAL_PLAYER_EMAIL or GLOBAL_PLAYER_PASSWORD is unset, and again if
    Gigya's response doesn't look like a successful login (non-zero
    errorCode, or a 200 response missing the fields a real success always
    carries) — this codebase never guesses a session is valid."""
    if not config.GLOBAL_PLAYER_EMAIL or not config.GLOBAL_PLAYER_PASSWORD:
        raise RuntimeError(
            "GLOBAL_PLAYER_EMAIL/GLOBAL_PLAYER_PASSWORD are not set. heart_global.login() needs a real "
            "personal Global Player email+password (see docs/build-log.md for the accepted-risk note) — "
            "this codebase never invents or requests real credentials, so set these yourself before calling it."
        )

    resp = client.post(
        _GIGYA_LOGIN_URL,
        data={
            "apiKey": _GIGYA_API_KEY,
            "loginID": config.GLOBAL_PLAYER_EMAIL,
            "password": config.GLOBAL_PLAYER_PASSWORD,
            "sessionExpiration": "0",  # session-only — fresh login every run, nothing persisted
            "format": "json",
        },
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()

    error_code = data.get("errorCode")
    if error_code not in (0, None):
        raise RuntimeError(f"Gigya login failed: errorCode={error_code} errorMessage={data.get('errorMessage')!r}")

    uid = data.get("UID")
    uid_signature = data.get("UIDSignature")
    signature_timestamp = data.get("signatureTimestamp")
    if not uid or not uid_signature or not signature_timestamp:
        raise RuntimeError(
            f"Gigya login response missing expected UID/UIDSignature/signatureTimestamp fields: {data!r}"
        )

    return _derive_bff_token(uid, str(uid_signature), str(signature_timestamp))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    promos, channels = ingest()
    for p in promos:
        print(f"[{p.entry_deadline or '?'}] {p.title}")
