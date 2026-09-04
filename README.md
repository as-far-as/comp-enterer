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

## Next steps (not built yet)

1. The entry-execution engine (spec section 5) — a Playwright script that
   actually fills and (once approved) submits a web-form entry, using
   stored `UserProfile` data. The Telegram bot above already gets you to
   "tap approve" — this is what would make that tap do something real.
