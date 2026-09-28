# Radio Competition Entry Assistant

Personal automation project — see the project's `technical-specification.md` and
`scoping-research.md` for the full design and the research behind it. This repo
is Phase 0 of the build plan: data model, storage layer, and the first working
discovery adapter, all runnable locally today with **no GCP project required yet**.

## What's here right now

- `src/radiocomp/models.py` — the full data model (Station, Promotion, TandCSnapshot,
  EntryChannel, EntryRecord, Outcome, UserProfile), as Pydantic models.
- `src/radiocomp/storage/` — a storage layer with three interchangeable
  backends, picked purely by `STORAGE_BACKEND`: a local JSON store (the
  default, writes to `data/*.json`), a Firestore store (for local dev,
  using your own account's credentials), and a Cloud Storage-backed JSON
  store, `gcs_json.py` (what Cloud Run Jobs use — Cloud Run's runtime
  service account can't reach Firestore on this project, confirmed by
  actually running a real Cloud Run Job against it; see docs/build-log.md,
  2026-09-02/03). Nothing outside `storage/` needs to change when you switch.
- `src/radiocomp/aggregators/loquax.py` — a working, tested discovery adapter
  against Loquax's live radio-competitions listing. Run it yourself:

  ```bash
  pip install -r requirements.txt
  PYTHONPATH=src python -m radiocomp.aggregators.loquax
  ```

  First run pulls whatever's currently listed into `data/promotions.json`; run it
  again and you'll see "0 new" since it dedupes against what it already knows.

- `src/radiocomp/compliance/` — first pass at the compliance engine (spec
  section 4): `tandc.py` captures a `TandCSnapshot` of a promotion's own
  page (narrow, phrase-based parsing — see its docstring for why it stays
  shallow rather than trying to summarise arbitrary T&C prose), and
  `engine.py` checks the two things spec section 4 names before anything
  should be entered — already-entered, and cross-brand shared-limit
  duplicates (Global's Heart/Capital/Smooth/Classic FM/LBC/Radio X share
  one entry limit; a live example of exactly this — the same TUI gift-card
  promotion under both Smooth Radio and Radio X — is what
  `test_compliance_engine.py` checks against). No entry-execution engine
  exists yet to actually gate, so this doesn't block anything on its own —
  it surfaces what that engine will need to check once it does.
- `src/radiocomp/run_discovery.py` + `Dockerfile` — the scheduled-run
  entrypoint and its container image. This is what actually runs hourly on
  Cloud Run now — see the "live and scheduled" update below.
- `src/radiocomp/notify/` + `src/radiocomp/webhook/` — the Telegram bot
  (push notifications with Approve/Skip buttons, plus the Cloud Run
  Service that receives the taps) — see the "Telegram bot" update below.
- `tests/` — offline tests against saved real HTML fixtures, so they don't
  depend on any live site looking a particular way on any given day.

## Update — first direct-station monitor built (talkSPORT)

`src/radiocomp/stations/talksport.py` is the spec's first "direct monitoring"
adapter, as opposed to the aggregator-ingestion pattern in `aggregators/`.
Two things worth knowing before you extend it to other stations:

- **It doesn't use Playwright.** Plain `httpx` reaches talkSPORT's pages fine —
  the "blocked" result from the original research was specific to that
  session's fetch-tool proxy, not a general block. Worth checking per-station
  before reaching for headless Chromium; it's slower and heavier for no
  reason on a site that doesn't need it.
- **Entry-channel classification is deliberately conservative.** Real
  talkSPORT competitions were messier than expected: a channel labelled
  "Free phone entry" turned out to mean "billed at your standard network
  rate" (a legitimate free route under the Gambling Act's definition, but not
  literally £0), and "Online" entry cost is often only shown on the live
  entry widget, not in the page text, so it can't be classified from a static
  fetch at all. Rather than guess, every `EntryChannel` the adapter can't
  confidently classify comes back with `is_free_route=None` and
  `review_recommended=True` — safe by construction, since the whole point of
  this field is to gate what the entry-execution engine is ever allowed to
  touch automatically. Run `python -m radiocomp.stations.talksport` yourself
  to see this live: most `web_form` channels currently come back `[REVIEW]`
  rather than confidently `[FREE]` or `[PAID]`, and that's the correct
  behaviour, not a bug to silence.
- Prize-value extraction is title-only for the same reason: a body-text
  fallback was tried and, on a live page, picked up the SMS entry cost
  (£2.50) as the "prize value" for a trip competition with no £ figure in its
  headline. Better to leave `prize_value_gbp` as `None` than ship a wrong
  number into the EV model.

## Known gap: no Ofcom bulk register, resolved with a manual seed instead

The Ofcom licensed-radio-stations register was meant to seed the `Station`
directory (per the spec, section 3) for the local/independent tier. Investigated
properly on 2026-09-02 (data.gov.uk/CKAN's Ofcom datasets, the current
ofcom.org.uk site) — no current, bulk-downloadable register turned up: the
only bulk file that exists (Ofcom's TxParams technical-parameters CSVs) is
dated March 2019 with dead file URLs, and the live site's "Look up radio
station details" tool looks like a single-record lookup, not an export or
API. Full trail in `docs/build-log.md`.

So: `src/radiocomp/stations/seed_local_independent.py` seeds a manually-picked
first tranche instead (14 stations, each checked live before inclusion — see
that file's docstring for what got dropped along the way and why, including a
few that turned out to have been quietly absorbed into Bauer's Greatest Hits
Radio network). Run it with:
```bash
python -m radiocomp.stations.seed_local_independent
```
It's idempotent (upserts by name). Treat this as a starting point to correct
or extend, not an authoritative register — no `ofcom_licence_ref` is set for
any of these, since that data isn't available from this seed.

## Setting up the GCP project (your side)

This is the one part that has to happen outside of this conversation — creating
a Google Cloud project and attaching billing isn't something that can be done on
your behalf. It's about 10 minutes:

1. **Create the project.** [console.cloud.google.com](https://console.cloud.google.com) →
   New Project. Pick a project ID you're happy to see in URLs and logs (e.g.
   `radio-comp-assistant`).
2. **Attach a billing account.** You'll need a card on file even to use the
   Always Free tier — you won't be charged as long as usage stays within it
   (see the technical spec, section 10, for exactly what "within it" means for
   this project).
3. **Set a budget alert immediately**, before building anything else: Billing →
   Budgets & alerts → Create budget. £2–5/month is plenty as a tripwire —
   the point isn't the amount, it's getting an email if anything ever pushes
   past the free tier.
4. **If you run more than one Google account** (e.g. this project's GCP
   account is separate from a work account also logged into gcloud/VS Code
   elsewhere), isolate this project's CLI identity *before* running any
   `gcloud` commands against it, so a stray command in the wrong terminal
   can't hit the wrong project:
   ```bash
   gcloud config configurations create radio-comp   # inactive until targeted
   gcloud config set project YOUR_PROJECT_ID --configuration=radio-comp
   gcloud config set run/region europe-west2 --configuration=radio-comp
   ```
   Then, rather than `gcloud config configurations activate radio-comp`
   (which changes the *global* active config — every terminal, every VS
   Code window, until switched back), scope it per-shell with
   `CLOUDSDK_ACTIVE_CONFIG_NAME=radio-comp`, so other terminals working on
   other projects are never affected. This repo's `.envrc` already sets
   that (plus loads `.env`) automatically whenever a shell `cd`s into it,
   via [direnv](https://direnv.net/):
   ```bash
   brew install direnv
   echo 'eval "$(direnv hook zsh)"' >> ~/.zshrc   # once per machine; restart terminal after
   direnv allow                                    # once per repo, from inside it
   ```
   With that in place, any `gcloud auth login` / `gcloud services enable` /
   etc. you run from a terminal opened in this folder targets `radio-comp`
   (and the right account, once you log in — see next step) without
   touching your other configs.
5. **Log into the Google account tied to this project** (from a terminal in
   this folder, so `radio-comp` is active per step 4): `gcloud auth login`.
6. **Enable the APIs this project needs:**
   ```bash
   gcloud services enable \
     run.googleapis.com \
     cloudscheduler.googleapis.com \
     firestore.googleapis.com \
     storage.googleapis.com \
     secretmanager.googleapis.com \
     cloudbuild.googleapis.com \
     artifactregistry.googleapis.com
   ```
7. **Create the Firestore database** (native mode, not Datastore mode):
   ```bash
   gcloud firestore databases create --location=europe-west2
   ```
8. **Region choice: `europe-west2` (London), with one exception for Cloud
   Storage.** Cloud Run, Firestore, and Cloud Scheduler's Always Free tiers
   all work fine in `europe-west2`, so this project standardises on it there
   — lower latency for a UK-based user, no free-tier cost. Cloud Storage's
   Always Free tier, however, is only available in `us-west1`, `us-central1`,
   and `us-east1` — so if a Storage bucket is ever created for this project,
   it should be created in `us-central1` specifically, even though everything
   else stays in `europe-west2`. Don't "fix" this into one region.
9. **A dedicated app service account was tried and abandoned — this project's
   account can't have one.** The original plan here was a `radio-comp-app`
   service account with a downloadable key (or, failing that, impersonation),
   so the running app's GCP identity wouldn't depend on whichever personal
   account happens to be logged into gcloud/VS Code — same reasoning as step
   4, but for the code rather than the CLI. In practice, this project sits
   under a Google Cloud organization (`183072770325`) that neither the
   project Owner nor Claude Code could administer, and that organization
   enforces (a) a policy blocking service-account key creation, and (b) an
   opaque Deny policy — confirmed via the IAM Policy Troubleshooter, which
   showed the underlying role as Granted but the resource's Deny policy as
   "you don't have permission to view" — that blocks *any* service account
   (regardless of role) from actually reading or writing Firestore. This
   matches Google's automatic "default organization" wrapper for projects
   created from a personal (non-Workspace) account: a security baseline the
   account owner doesn't get to edit. Full diagnostic trail in
   `docs/build-log.md`'s 2026-09-02 entries if this needs revisiting — e.g.
   if the project ever moves under a real Cloud Identity/Workspace org, or
   Google Support turns up a way to relax it.
10. **So: local dev uses your own account's credentials directly** — no
    service account, no impersonation:
    ```bash
    gcloud auth application-default login --configuration=radio-comp
    ```
    This is exactly the "no isolation" fallback step 4 was trying to avoid,
    but it's what's actually available here.

    Worth being honest about a real gap in this: Application Default
    Credentials is a single **global** file
    (`~/.config/gcloud/application_default_credentials.json`), not scoped
    per gcloud configuration the way `radio-comp` vs `default` are. If you
    also use ADC for other work (a data pipeline, another project), running
    `gcloud auth application-default login` there will silently overwrite
    this project's ADC, and vice versa — this actually happened once during
    this project's own setup. There's no clean fix short of re-running the
    login command for whichever project you need next; just know it's a
    manual swap, not a permanent one.
11. **Cloud Run's runtime identity hits the exact same Firestore wall —
    confirmed by actually running a real Cloud Run Job against it**, not
    just inferred from the local test above. It failed with the identical
    `403 Missing or insufficient permissions`. The same check against
    **Cloud Storage**, though, worked fine — so `STORAGE_BACKEND=gcs`
    (`gcs_json.py`) is what anything running on Cloud Run uses instead of
    Firestore. This needs its own bucket, created in `us-central1` per the
    region rule in step 8:
    ```bash
    gcloud storage buckets create gs://YOUR_PROJECT_ID-data --location=us-central1
    gcloud storage buckets add-iam-policy-binding gs://YOUR_PROJECT_ID-data \
      --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
      --role="roles/storage.objectAdmin"
    ```
    (`YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com` is Cloud
    Run's default runtime identity unless you configure a custom one —
    find the project number via `gcloud projects describe YOUR_PROJECT_ID`.)
    Cloud Build's default service account needs its own routine grants too,
    the first time you build/push an image on a project that's never used
    Cloud Build before — `roles/storage.objectViewer` (to read its own
    upload) and `roles/artifactregistry.writer` (to push), both on the same
    default compute service account, both project-level bindings, both
    one-time setup.

Once that's done, copy `.env.example` to `.env` and fill in:

```
STORAGE_BACKEND=firestore   # local dev
GCP_PROJECT_ID=your-project-id
```

or, for anything running on Cloud Run:

```
STORAGE_BACKEND=gcs
GCP_PROJECT_ID=your-project-id
GCS_BUCKET_NAME=your-project-id-data
```

`google-cloud-firestore`/`google-cloud-storage` pick up ADC (locally) or the
runtime service account (on Cloud Run) automatically — no code changes, no
`GOOGLE_APPLICATION_CREDENTIALS` needed. (That variable is still supported
by `config.py`/`firestore_store.py` for a service-account-key setup, in
case a future account/org allows one.)

## Update — live and scheduled: Cloud Scheduler → Cloud Run Job

The full discovery pipeline now runs on its own, hourly, without your
laptop. `src/radiocomp/run_discovery.py` is the entrypoint for three of the
four adapters (theprizefinder, talksport, radioexe) — it runs each one,
catching and logging errors independently so one station breaking doesn't
take the others down; it only exits non-zero if *every* adapter failed.
The `Dockerfile` builds a lean image around just that (no Playwright, no
Firestore client — see the Dockerfile's own comment for why), pushed to
the `radio-comp` Artifact Registry repo. A Cloud Run Job
(`radio-comp-discovery`, `STORAGE_BACKEND=gcs`) runs it, and a Cloud
Scheduler job (`radio-comp-discovery-hourly`, `0 * * * *`, Europe/London)
triggers it — confirmed end-to-end with a real manual trigger, not just
configured on paper: Scheduler → Cloud Run Job → completed successfully →
new promotions landed in the real `project-a6778446-201f-4aa5-a03-data`
bucket.

**Loquax runs separately**, via its own scheduled GitHub Actions workflow
(`.github/workflows/loquax-scheduled.yml`) rather than this Cloud Run Job —
Loquax outright bans Google Cloud's shared egress IP range (`Your IP
address has been banned.`, confirmed live), but GitHub Actions' runners
aren't banned, confirmed the same way before building anything further.
Auth is via Workload Identity Federation rather than a service-account key
(still blocked on this project's org) — GitHub's own OIDC token gets
exchanged for short-lived GCP credentials on each run, trust scoped
specifically to this repo. See docs/build-log.md for the full
investigation and setup.

## Update — a way to actually look at what's been found

Until now, the scheduled job's output only existed as raw JSON — readable
with `gcloud storage cat`, not really readable by a person. `src/radiocomp/
view_promotions.py` is the smallest fix for that: lists every known
`Promotion`, soonest deadline first, with its `EntryChannel`s
(FREE/PAID/REVIEW, same flags each adapter's own CLI output uses) and a
compliance-engine check (spec section 4) run against it inline — so an
already-entered or cross-brand-duplicate promotion shows a `!!` note right
there, no separate step needed. Reads whatever `STORAGE_BACKEND` is
configured, same as every adapter — point it at `local`, `firestore`, or
`gcs` (the real scheduled data) via `.env`. Run it:
```bash
PYTHONPATH=src python -m radiocomp.view_promotions
```
Superseded by the Telegram bot below for anything you'd actually act on —
`view_promotions.py` is still handy as a quick full-list check, but new
promotions now push to you instead of needing to be pulled.

## Update — the Telegram bot: notify + approve/skip

The human-in-the-loop surface from spec section 6 is live: every newly
discovered promotion gets pushed to you as a Telegram message (title,
station, prize, deadline, entry channels with the same FREE/PAID/REVIEW
flags, and a compliance-engine warning if it's a duplicate/already
entered). When — and only when — a promotion has exactly one channel
that's confidently free and doesn't need review, the message also gets
**Approve**/**Skip** inline buttons; tapping one records your decision as
an `EntryRecord` and edits the message to confirm it. Anything without a
clearly safe channel (nothing extracted yet, or everything's paid/needs a
look) sends as a plain notification instead — same "don't guess" posture
as the rest of this codebase, just translated into "no button" instead of
"no guess".

**Scope, deliberately**: Approve only ever *records* a decision. It
doesn't fill in or submit a real form — there's no entry-execution engine
yet (spec section 5), and no `UserProfile` data collected. That's a
distinct, bigger, future step; this one is "discover → notify → tap →
recorded", fully real and fully working end to end.

Architecture: `src/radiocomp/notify/` (outbound, plain `httpx` calls to
the Telegram Bot API — no `python-telegram-bot`, no `parse_mode`/Markdown,
see that package's docstrings for why) runs from both `run_discovery.py`
(Cloud Run Job) and `loquax.py`'s own `__main__` (GitHub Actions).
`src/radiocomp/webhook/` is a small FastAPI app, deployed as its own Cloud
Run **Service** (`radio-comp-webhook`, `Dockerfile.webhook` — separate
from the discovery Job's image, since the webhook needs FastAPI/uvicorn
and the Job doesn't), that receives Telegram's button-tap callbacks. It's
`--allow-unauthenticated` (Telegram's own servers can't do GCP IAM auth),
protected instead by Telegram's `X-Telegram-Bot-Api-Secret-Token` header
mechanism — see `webhook/app.py`'s docstring.

Setting this up yourself (secrets shouldn't pass through an AI agent's
tool calls):
1. Create a bot via **@BotFather** on Telegram, get the token.
2. Message it once, then `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"`
   to read back your chat ID.
3. `printf '%s' "<token>" | gcloud secrets create telegram-bot-token --data-file=-`
   and `printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create telegram-webhook-secret --data-file=-`
   (both `--configuration=radio-comp`). Use the `printf '%s' "$(...)"`
   wrapper, not a raw pipe from `openssl rand` — `openssl rand -hex 32`
   prints a trailing newline, which a raw pipe stores as part of the
   secret; Telegram's own registered value never has one, so the two
   silently stop matching. (`webhook/app.py` now `.strip()`s at comparison
   time regardless, so this isn't load-bearing anymore, but a clean secret
   is one less thing to think about.)
4. Add `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` as GitHub repository secrets
   for the Loquax/GitHub Actions path.
5. Once the webhook Service is deployed, register it yourself (needs the
   raw token in the URL):
   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=<service-url>/telegram/webhook" \
     -d "secret_token=<the telegram-webhook-secret value>" \
     -d 'allowed_updates=["callback_query"]'
   ```
6. Don't call `getUpdates` again afterward — Telegram only delivers to one
   mechanism at a time, and polling silently breaks webhook delivery.

**A real credential leak found and fixed during setup, worth knowing
about**: `httpx` logs the full request URL at INFO level, and Telegram's
Bot API puts the bot token directly in the URL path
(`api.telegram.org/bot<TOKEN>/...`) — so until this was caught, every
outbound call logged the live token straight into Cloud Logging. Fixed by
setting the `httpx` logger to `WARNING` in every entrypoint that imports
`notify/` (`run_discovery.py`, `loquax.py`'s `__main__`, `webhook/app.py`).
If you're re-provisioning this bot, rotate the token afterward regardless
(`@BotFather` → `/mybots` → your bot → API Token → Revoke) — treat an
exposed credential as compromised even once the leak itself is fixed.

See docs/build-log.md for the full build/deploy trail.

## Update — the entry-execution engine: drafting and submitting real entries

Spec section 5 is now live: tapping Approve on a qualifying `web_form`
channel makes something real happen, not just a recorded decision. A hard
finding shaped this design — checked against real production data before
building anything: at the time this was written, **zero** discovered
`EntryChannel`s were `web_form` *and* confidently free *and* not flagged
for review (every real "approvable" channel so far is `post` or
`phone_entry` — both explicitly non-automatable, no exceptions, see
CLAUDE.md). This engine is built for the promotion that *will* eventually
qualify, verified against a realistic hand-built fixture form
(`tests/fixtures/entry_execution/sample_entry_form.html`), not a
manufactured real case.

**Two-stage, human-approved, LLM-assisted field mapping — never
per-site-hardcoded selectors:**
1. **Draft.** `entry_execution/draft.py` opens the entry page with
   Playwright, extracts every field's selector/label/type/options
   (`browser.py` — tags each field with its own `data-rc-field` marker
   rather than trusting the page's own ids, and deliberately hands the LLM
   this structure, never raw HTML or a screenshot, since raw HTML invites
   a hallucinated selector and a screenshot alone still can't produce a
   working one), sends *only that structure* — never any actual personal
   data — to Gemini (`llm_mapping.py`, `gemini-3.8-flash` — switched from
   Claude 2026-09-08 so this isn't tied to a work Anthropic account; a
   free-tier personal-Google-account key is plenty given how rarely this
   runs) to classify each field as a known profile field, a checkbox (required-consent → check,
   anything marketing/ambiguous → leave unchecked, "when in doubt, leave
   unchecked"), a creative/skill-based question, or unmappable.
   `fill_plan.validate_mapping()` then re-verifies the LLM's response
   against the real page before trusting it at all (every selector must be
   one we actually sent, no duplicates, field count matches) — the same
   "never trust the model's output as-is" posture this codebase already
   applies to every adapter's own extraction. A creative or unmappable
   field means the whole draft is refused — you get a plain "worth your
   five minutes" notification instead, never an auto-generated tie-breaker
   answer. Otherwise your real `UserProfile` values (name/DOB/address/
   phone/email — set up once via `python -m radiocomp.setup_user_profile`,
   entered directly in your own terminal, never through this
   conversation) get filled in, a screenshot goes to Telegram with
   **Submit**/**Reject** buttons, and nothing is submitted yet.
2. **Submit.** Tapping Submit marks the draft `APPROVED`; the next
   scheduled tick's `submit.py` re-navigates to the page, **re-extracts
   its fields from scratch** (confirmed by test that this re-tagging
   reassigns identical selectors in the same order, as long as the form's
   structure hasn't changed), verifies every selector the saved plan needs
   still exists, and only then replays the *exact same* saved fill
   plan — no second LLM call, so nothing about the submission depends on
   a fresh model response. A form that's changed shape since the draft is
   refused, not guessed at. A submission failure or a changed-shape
   refusal both land as `FAILED` with a screenshot and a message, never
   silently.

`channel_type == web_form` is checked as its own explicit, standalone
condition in three independent places (draft eligibility, submit
eligibility, and a defensive check in `submit.py` itself refusing to ever
submit a record with no saved fill plan) — never inferred from
`is_free_route`/`review_recommended` alone, since real data showed those
two fields alone don't encode the phone/post ban. A pre-existing gap this
also fixed: the original Approve/Skip notification path
(`notify/channel_selection.py`) had no channel-type awareness at all,
which would have put an immediate, unreviewed Approve button on a future
free `web_form` channel — that channel type is now excluded from that path
entirely, so a `web_form` channel only ever reaches you through the draft
flow above.

**Results tracking (spec section 7), kept small**: once a `SUBMITTED`
entry's promotion deadline has passed (plus a few days for a station to
actually announce a winner), `outcomes/reminder.py` asks once — a plain
Telegram message with **Won**/**Didn't win** buttons, reusing the same
callback machinery. No further follow-up beyond that single ask.

Both stages plus the outcome check run from one new entrypoint,
`run_entry_execution.py`, on its own Cloud Run Job
(`radio-comp-entry-execution`) and Cloud Scheduler cadence (`*/15 * * * *`
— frequent enough that a Submit tap gets acted on promptly; most ticks
find nothing eligible and exit before Playwright ever launches). Its own
image, `Dockerfile.entry-execution`, is based on
`mcr.microsoft.com/playwright/python` rather than hand-installing Chromium
onto `python:3.13-slim` like the other two images — that image's tag must
stay pinned to exactly the `playwright==` version in `requirements.txt`
(a mismatch means Playwright can't find its browser executable at all).

Setting this up yourself:
1. `python -m radiocomp.setup_user_profile` — run locally; prompts for
   your real name/DOB/address/phone/email and saves them directly to
   whichever `STORAGE_BACKEND` is configured. `--check` afterward prints a
   masked summary (name in full, everything else redacted) so you can
   confirm it saved without redisplaying the real values.
2. Get a free-tier key from aistudio.google.com (a personal Google
   account, no billing required), then create the secret yourself:
   ```bash
   printf '%s' "<key>" | gcloud secrets create gemini-api-key --data-file=- --configuration=radio-comp
   ```

See docs/build-log.md for the full build/deploy trail. The entry-execution
engine has since been verified working end to end for real (a genuine
draft → Telegram approval → real browser submission), on Gemini rather
than Claude (switched 2026-09-08 so it isn't tied to a work Anthropic
account) — see the next update for what's actually feeding it real
qualifying channels now.

## Update — talkSPORT's "Online" channel: reaching real pricing behind a third-party widget

The entry-execution engine above had nothing to actually do: real data
showed zero `web_form` channels were ever confidently free. Breaking that
down (30 discovered channels), 9 were `web_form`, but 7 sat permanently
`is_free_route=None` — talkSPORT's real entry cost for "Online" isn't in
the competition page's own HTML at all, rendered or not: it's delegated to
a third-party competition-entry platform (`win.talksport.com`) behind a
cross-origin, natively lazy-loaded iframe, sometimes behind a cookie-
consent modal too. `src/radiocomp/stations/talksport_widget.py` reaches it
for real — the right User-Agent (this project's existing polite,
self-identifying one; Chromium's default headless UA got the widget into
the DOM 0/6 times in testing, this project's UA got it 5/5), a
consent-dismiss, a forced scroll to trigger the lazy-load, then reading
the widget's own text (a different phrasing convention entirely from the
outer page — "£X PER ENTRY", not "charged at £X"). A bounded retry
(3 attempts, fresh browser each time) covers the widget's real
appear-intermittently behaviour, confirmed live. Same "never guess"
posture as everywhere else in this codebase: if the widget doesn't
appear, or its text doesn't match a known pattern, the channel stays
exactly as ambiguous as it started.

Run against real production data: **4 of 7 ambiguous channels resolved to
confidently paid** (`£2.50 per entry`); the other 3 correctly stayed
ambiguous — their live pages no longer even mention an "Online" entry
method (content drift since the original scrape, not a bug). Stated
honestly: this pricing-tier widget looks like a shared template across
talkSPORT's whole platform, so it's plausible none of these ever resolve
to *free* — the real value is turning "stuck at unknown forever" into an
audited, confident classification, not (so far) a new qualifying channel.
A one-off backfill (`python -m radiocomp.stations.backfill_rendered_classification`)
resolves the existing backlog; new talkSPORT discoveries get the same
treatment automatically going forward. `radio-comp-discovery`'s own image
and Cloud Run Job resources were updated to match (Playwright now needed
there too, same base-image pattern as `Dockerfile.entry-execution`).

Radio Exe got a smaller, independent fix alongside this: its web-form
detection previously required a specific cost phrase to create a channel
*at all* — a genuinely free web form produced no channel whatsoever
(silent omission), not an ambiguous one. Fixed with a presence-only
signal; unrelated to the talkSPORT mechanism above, since Radio Exe's
pages are already fully server-rendered.

See docs/build-log.md for the full investigation trail, including a
self-inflicted finding worth knowing about if this code is ever
hand-tested again: enough manual back-to-back live requests in a short
window (several dozen within ~20 minutes) triggered talksport.com's own
bot-detection into serving a "Verifying Device" challenge page instead of
real content, to plain `httpx` requests too — not a Playwright-specific
issue, and not expected to recur under normal scheduled usage (once per
promotion per hourly run), but worth pacing manual testing accordingly.

## Update — a new discovery source: Bauer's "Make Me A Winner"

Discovery volume wasn't meeting expectations — only 2 aggregators and 2
direct station monitors were live, against an original plan naming 3
aggregators plus Global, Bauer, and talkSPORT as target networks (only
talkSPORT ever got built). `src/radiocomp/stations/bauer_makemeawinner.py`
is a new direct monitor for Bauer Media's shared "Make Me A Winner"
competition — syndicated across Absolute Radio, Kiss, Magic, Hits Radio,
Greatest Hits Radio, and Planet Rock, one adapter covering six stations
at once. Its site (`makemeawinner.co.uk`) is a pure client-rendered SPA
with nothing in a plain fetch, but it turned out to have a clean,
unauthenticated JSON API behind it (`api.winhappy.com`) — a short-lived
guest session token from one endpoint authorizes a second that returns
every live competition with a genuine `is_free` boolean straight from
Bauer's own backend. That's confirmed via plain `httpx` alone, no
Playwright needed, and it's the first source in this codebase where
free/paid classification is a real field from the source system rather
than a regex guess against scraped text — confident in both directions,
never needing a review flag unless the field itself is missing.

A companion investigation into Global's Heart brand found a real safety
concern instead: loading one of its off-page entry subdomains
(`comp.heart.co.uk`) with Playwright — no click, no form fill — showed
"Thank you! You have successfully entered the competition." Verified
carefully rather than assumed: the message appeared *immediately* on
load (too fast for a real submission), and network-request monitoring
showed only a routine consent-tracking call, nothing resembling a
submission — a front-end bug in Heart's widget (it depends on a real
login to Global's own Gigya SSO system and shows a misleading default
state without one), not a real entry. Dropped Heart for this phase
regardless — its actual entry mechanism needs a genuine personal login to
a third-party account system, a bigger category of credential than this
project has taken on before, and a platform that misleads when read
passively isn't worth building against right now. `compliance/engine.py`'s
`SHARED_LIMIT_NETWORKS["Bauer"]` was extended with Magic, Hits Radio, and
Planet Rock alongside this (confirmed live, closing a gap already flagged
in that module's own docstring).

Verified for real: a live discovery run added **15 new promotions in one
pass** (real volume, not a projection) with confident classifications —
all 15 happen to be paid today, matching the pattern already found for
talkSPORT's own widget, but the classification is a real field now, not a
guess, so a genuinely free Bauer competition will be caught immediately
and correctly whenever one appears.

**Update, same day** — the user found a real gap in the above by actually
using the system: a "paid" campaign turned out to have a genuinely free
phone-line entry route, which `bauer_makemeawinner.py` hadn't recorded at
all (the design already called for this; the implementation shipped
incomplete). Fixed — the adapter now also extracts a free `PHONE_ENTRY`/
`POST` channel from each campaign's own T&Cs when one exists, so it shows
up in the Telegram notification alongside the paid web form. To be
explicit, since this comes up often enough to restate: this only makes
the free route *visible*; phone entry itself is never automated,
full stop, per CLAUDE.md. Also resolved the "250 free entries" figure
from the original research — it was the phone route's own weekly cap, not
a web-form limit. Backfilled the 15 promotions already in production
(12 channels added) via `python -m
radiocomp.stations.backfill_bauer_phone_post_channels`. See
docs/build-log.md for the full trail.

## Update — pivoted to local stations; a real find, then a residency mismatch

Every major-network source built so far routes through a monetized
platform with no free web form. Live investigation found a genuine
exception — Central FM's "Wake Up & Cash In" is a real, live, plain
native HTML form (no third-party platform, no cost, running on the
"Aiir" CMS already referenced in `radioexe.py`'s own docstring, now
confirmed on 3 stations) — but its own T&Cs require Forth Valley
(Scotland) residency, and the user's real postcode is SE5, South-East
London. None of the 13 stations in `seed_local_independent.py` were ever
checked against where the user actually lives; hyper-local commercial
radio exists to serve a specific small catchment, so this is a structural
issue for the whole tier, not a one-off.

Re-targeted at genuine SE-London coverage: `seed_southeast_london.py`
seeds 4 real, currently-operating, Ofcom-licensed stations covering
Southwark/Camberwell (Select Radio, Rainbow Radio, Mi-Soul, Resonance
FM). Honest result: none currently has a live free competition. Built
`stations/watch_for_competitions.py` instead of a speculative
classifier — a minimal, real-data-free "has a Win-looking link appeared
on this homepage since last time?" check, folded into the existing
hourly discovery run, that notifies once (never repeats) so a proper
adapter can be built the moment one of these 4 stations actually has
something live to test against.

Separately, declined a direct request to automate the free phone-line
route found during the Bauer fix "in bulk," even though standard-rate
calls are covered by a personal phone allowance — the concern was never
really about cost. Ofcom's civil misuse regime doesn't turn on who pays,
station T&Cs explicitly ban bulk/automated entries, and a placed call has
no undo step. CLAUDE.md's phone-automation ban stands as originally
scoped.

## Update — a strategic reckoning: automation has a real ceiling, so we're investing in the manual step instead

Across every source built or investigated this project — talkSPORT,
Radio Exe, Bauer, Heart, 17 local/independent stations — **zero
genuinely free, automatable web-form entries have ever turned up in real
data.** The entry-execution engine works (built, deployed, mechanically
proven against a fixture) but has never fired for a real competition,
because nothing has ever qualified. The honest read: every real free
route actually found (a phone line, a postal address, an on-air-callback
form) has a built-in friction cost a web form doesn't — plausibly the
compliant "free alternative" doing its intended anti-bulk-entry job, not
a gap in how hard this project has looked. The system's actual proven
value has been discovery and visibility, not automation.

Two directions, in place of continuing to hunt for automation: make the
manual step easier without automating it, and keep expanding discovery
sources for visibility. Shipped the first one already: `formatting.py`'s
shared channel-line formatter was storing every phone/post/SMS/email/
WhatsApp channel's actual contact info (`channel_url_or_number`) since
early in the project, but never displaying it — the user found their one
real free route (a phone line) only by clicking through to the source
page themselves. Fixed — these channel types now show the actual number/
address/inbox directly in the notification and in `view_promotions.py`'s
CLI output. Phone numbers get free tap-to-call via Telegram's own
client-side auto-linking (no Markdown/HTML needed, consistent with this
project's permanent plain-text-only design).

## Update — a new discovery source: `xd.wayin.com` ("Grow by Zeta")

`src/radiocomp/stations/wayin.py` is a new adapter for `xd.wayin.com`
("Grow by Zeta"), a third-party competition platform with no listing API
or index of its own — unlike `bauer_makemeawinner.py`'s
`api.winhappy.com`, there's nothing to poll directly. Campaigns are found
instead by scanning a small, manually-maintained seed list of pages
already known to link out to one, same "seed manually, expand over time"
convention as the station-seeding files.

Two real linking pages were captured to build this (2026-09-11): KMFM's
own `/win/` page, and Hits Radio's (Bauer/Rayo's) own competitions page —
the original plan's exact two examples had both moved on since the
research session that first found them (STARTUPBUNDLE expired; its
Hits Radio successor now embeds via a *different* platform,
`display.engagesciences.com`, not wayin.com), so the real, currently-live
Bauer example used instead is a shared Tesco Clubcard competition found
the same way. A genuine wrinkle found via real testing: KMFM's page has
a plain `<a href="https://xd.wayin.com/...">` link, exactly as the plan
assumed, but Rayo's own site is a client-rendered Next.js app whose
wayin.com URL is never a real link at all — it only exists as a string
inside the page's embedded JSON state, rendered into a widget
client-side. `find_wayin_links()` has to scan both ways (a normal link
scan, plus a raw text/JSON regex scan) to catch both real shapes; the
plan's original "just scan `<a href>`" assumption would have silently
found nothing on the Bauer/Rayo side.

Both real wayin.com campaign pages turned out to be plain, server-
rendered HTML — no Playwright needed, confirmed empirically. Free/paid
classification stays fully conservative: only one of the two real
campaigns says anything explicit about cost at all (KMFM's own campaign
T&Cs state "Online entry is free of charge." verbatim); the other has no
cost language anywhere in its static HTML, so it comes back
`is_free_route=None, review_recommended=True` rather than guessing "free"
from an entry form with no payment fields. KMFM itself is owned by KM
Media Group, not Bauer, but its campaign's own T&Cs describe it as a
shared Bauer-network competition (the same cross-brand entry limit as
every other Bauer station), so it's modelled with `network="Bauer"`,
confirmed from that campaign's own T&Cs rather than assumed from KMFM's
on-air branding.

Verified for real: a live discovery run found both real campaigns
correctly, with the KMFM one classified confidently free and the Tesco
Clubcard one correctly left for review — and a full `run_discovery.py`
pass with all 5 adapters registered completed with 0 failures.

## Update — Heart/Global Player, and it needed no login after all

`src/radiocomp/stations/global_win.py` (renamed from `heart_global.py` —
see the next update) is a new adapter for `winplus.heart.co.uk`, Global's
own first-party "Global WIN" competition platform, shared network-wide
(Heart, Capital, Classic FM, Gold, LBC, Radio X, Smooth) via per-brand
instances — the same "one adapter, several stations" shape as
`bauer_makemeawinner.py`. Heart was dropped back in
early September after one of its off-page entry subdomains showed a
misleading "successfully entered" state when read anonymously, on the
assumption that reaching real free/paid status meant a genuine personal
login to Global's Gigya SSO. Revisiting it found that assumption didn't
hold for the platform that actually matters: a real `winplus.heart.co.uk`
competition page, fetched with no login attempted at any point, plainly
shows both `"FREE ENTRY: No purchase necessary."` and `"Paid entry from
£X..."` text on the same page — sign-in is only needed to *submit* an
entry, never to *read* its free/paid status. So this adapter's
discovery/`ingest()` needs no credentials at all, same as every other
adapter here.

A second real find while building it: `winplus.heart.co.uk` itself is a
pure client-rendered Vue SPA (a plain fetch gets nothing but an empty
shell), but its real content turned out to come from a clean,
unauthenticated JSON API served from the same origin — found via
Playwright network-request capture, then confirmed to work through plain
`httpx` alone, no Playwright needed for this adapter at all. Same
discovery shape as `bauer_makemeawinner.py`'s own `api.winhappy.com`, and
a second source in this codebase where free/paid comes from a genuine
field in the source system (`competitionEntryType`), not a
text-classification guess — confident in both directions. Every real paid
competition has exactly one genuine free "no purchase necessary"
alternative (a phone route or a postal route, never both) described only
in its own T&Cs — tracked for visibility only, per this project's
permanent no-phone-automation rule.

A standalone `login()` also exists, implementing Global's real Gigya SSO
login flow (confirmed live, passively, never actually attempted) — built
now because the user has separately signed off on taking on real personal
Global Player credentials for *future* entry-submission work, accepting
the real account-suspension risk if Global's anti-automation detection
ever flags it. It is **not** wired into `ingest()` or any scheduled path;
it only exists to be called on-demand, later, once real credentials
exist. See docs/build-log.md for the full mechanics and the accepted-risk
statement.

Verified for real: a live discovery run found 14 real live Heart
competitions correctly, a second run correctly deduped to 0 new, and a
full `run_discovery.py` pass with all 6 adapters registered completed
with 0 failures.

## Update — `global_win.py`: stopped filtering to Heart only

The adapter above was filtering out every competition not tagged with
Heart's own brand id before recording it. A live check of `init.json`'s
full brands map confirmed it's entirely Global's own portfolio (Heart,
Capital, Radio X, Smooth, Classic FM, LBC, Gold, Capital Xtra, Big Top 40,
Global Player, Riviera Radio) with the same shared backend and entry
mechanics regardless of which brand(s) display a competition — so
filtering to one brand was just throwing away real, otherwise-unreachable
competitions. `heart_global.py` → `global_win.py`, `STATION_NAME` →
`"Global WIN"` (the platform's own real branding), and `ingest()` now
records every non-hidden competition once, regardless of brand tagging —
same "one shared platform, one shared station name" precedent
`bauer_makemeawinner.py` already established, avoiding near-duplicate rows
if this module were ever pointed at more than one brand.

Verified for real: a live run found **16** competitions (up from 14
Heart-only), including genuinely non-Heart-branded ones this adapter had
been silently missing every run since it shipped — "Capital's Bong Game
2026" and a Manic Street Preachers/Suede ticket giveaway among them. Full
suite: 174 passed, 1 skipped.

## Update — recurring competitions notify once, not once per day

"Capital's Bong Game 2026" turned out to be a genuine daily round
(`competitionIsRound: true`, a shared `competitionScheduleId` across every
day's own separate competition), which would otherwise mean a fresh
Approve/Skip Telegram message every single day, indefinitely. `Promotion`
now has a `recurrence_series_id` field, set only from that genuine source
signal (never guessed), and `notify/send.py` only ever notifies the
earliest-deadline promotion sharing a series id — later occurrences are
silently skipped, and the one message that does go out says so. Approving
it never carries forward to future occurrences; each day's round is still
its own separate record needing its own human decision, same as
everything else here.

Loquax has been independently hitting this same competition every ~9 days
via its own forum thread, as separate unlinked promotions — a milder
version of the same problem, left unfixed since a forum aggregator has no
genuine recurrence field to key off, only a title string, and guessing
would break this project's "never infer what isn't really there" rule.

Full suite: 182 passed, 1 skipped.

## Update — Global WIN entry-execution: real authenticated draft/submit

A live investigation found why the entry-execution engine couldn't act on
any real, confidently-free Global WIN channel yet, precisely: zero
`<form>`/`<input>` elements exist anywhere in the DOM on a real competition
page until *after* "Step 1: Sign in with your global iD" completes — there
is no anonymous entry form at all, signing in is the entry mechanism
itself. A direct `goto()` to a competition's deep-link URL also reliably
crashes Global's own frontend JS on a cold load (a real bug in their SPA);
loading the relevant brand homepage first and clicking through in-app
loads the same page with zero errors.

New module, `entry_execution/global_win_auth.py`: `sign_in(page)` drives
the *real* Global Player sign-in form (`globalplayer.com/signin/`,
`#email`/`#password`, confirmed live) rather than reusing
`global_win.py`'s existing REST-only `login()` — driving the real form
lets Global's own JS set whatever session state each winplus subdomain's
frontend actually checks. `_resolve_homepage_for_competition()` maps a
competition's own `brands` array (from `/data/competitions/list.json`)
plus `/data/init.json`'s brand-code map to the one real winplus homepage
that features it (confirmed live that the generic `winplus.co.uk`
homepage does *not* list every competition — brand tagging genuinely
gates which homepage can reach a given one).
`open_authenticated_page()` launches, signs in, navigates to that
resolved homepage, dismisses consent, and clicks through to the target
competition by its numeric id — never a bare `goto()` of the deep link.

The Sourcepoint consent-dismiss idiom (`iframe[id^="sp_message_iframe"]`
+ "Accept") moved out of `stations/talksport_widget.py` into a shared
`browser.dismiss_consent_banner()`, now also used by the existing
anonymous `browser.open_page()` — a small, generically useful improvement
on its own, and confirmed live that globalplayer.com's own consent modal
uses the identical markup.

`draft.py`/`submit.py` route by `promo.station_name_raw ==
global_win.STATION_NAME`: a Global WIN channel goes through
`global_win_auth.open_authenticated_page`, everything else through the
existing `browser.open_page`. With no `GLOBAL_PLAYER_EMAIL`/
`GLOBAL_PLAYER_PASSWORD` configured, both fail closed immediately
(`EntryStatus.FAILED`, a clear `submission_error`) rather than attempting
anything.

**What was verified live** (2026-09-28, passively — page loads, DOM
inspection, no form ever submitted): the sign-in page's consent modal and
`#email`/`#password`/submit-button selectors; the homepage-click-through
mechanism, on both a brand-specific homepage (`winplus.radiox.co.uk`) and
the generic one (`winplus.co.uk`), against real live competitions, with
zero JS errors and full form content loaded after the click-through; that
`winplus.co.uk`'s own homepage genuinely doesn't list a competition tagged
only with other brands (proving per-competition homepage resolution is
necessary, not just a nice-to-have); and that every real winplus brand
subdomain in `_BRAND_CODE_TO_HOMEPAGE` resolves with a 200. **What remains
genuinely unverified**: the real sign-in submission itself (nothing was
ever typed into the form or submitted — `GLOBAL_PLAYER_EMAIL`/
`GLOBAL_PLAYER_PASSWORD` are deliberately not bound anywhere this
environment can reach) and, downstream of that, whether the resulting
session is actually recognised as signed-in by a winplus subdomain's own
frontend. Both are for the user's own first real run, once the two
Secret Manager secrets are bound to the `radio-comp-entry-execution` Cloud
Run Job.

Full suite: 194 passed, 1 skipped (pre-existing, unrelated — the live
Gemini mapping test).

## Next steps (not built yet)

Nothing from the original spec's core phases remains unbuilt. Open items
are refinements rather than new capabilities — see docs/build-log.md's
most recent entries for the current punch list. The competition watcher
above is a genuine "wait and see" — its real test is whether it catches
the next live competition on one of the 4 seeded SE-London stations. The
original 13 `seed_local_independent.py` stations are worth revisiting the
same way (checked against actual user geography) if this doesn't pan out.
MoneySavingExpert (named in the original spec, never built) is the next
concrete lead for more discovery volume; `xd.wayin.com` and Heart/Global
(above) are now both built. Heart/Global's `login()` is built but not yet
used for anything — actually calling it to submit an entry is a distinct,
not-yet-taken decision, gated on the user creating the real Secret
Manager credentials themselves.
