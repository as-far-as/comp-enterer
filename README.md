# Radio Competition Entry Assistant

Personal automation project — see the project's `technical-specification.md` and
`scoping-research.md` for the full design and the research behind it. This repo
is Phase 0 of the build plan: data model, storage layer, and the first working
discovery adapter, all runnable locally today with **no GCP project required yet**.

## What's here right now

- `src/radiocomp/models.py` — the full data model (Station, Promotion, TandCSnapshot,
  EntryChannel, EntryRecord, Outcome, UserProfile), as Pydantic models.
- `src/radiocomp/storage/` — a storage layer with two interchangeable backends:
  a local JSON store (the default, writes to `data/*.json`) and a Firestore store
  (stubbed, ready to switch on once your GCP project exists). Nothing outside
  `storage/` needs to change when you switch.
- `src/radiocomp/aggregators/loquax.py` — a working, tested discovery adapter
  against Loquax's live radio-competitions listing. Run it yourself:

  ```bash
  pip install -r requirements.txt
  PYTHONPATH=src python -m radiocomp.aggregators.loquax
  ```

  First run pulls whatever's currently listed into `data/promotions.json`; run it
  again and you'll see "0 new" since it dedupes against what it already knows.

- `tests/` — offline tests against a saved real HTML fixture, so they don't
  depend on Loquax's listing looking a particular way on any given day.

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

## Known gap, deliberately left open

The Ofcom licensed-radio-stations register was meant to seed the `Station`
directory (per the spec, section 3) for the local/independent tier — I wasn't
able to locate the right current dataset URL on Ofcom's site in this session
(their site structure has changed since older references to it). Worth a
follow-up look, or `data.gov.uk` may host the same register. Until then, local
station coverage can be seeded manually with a handful of stations you care about.

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
9. **Create a dedicated service account for the app itself**, rather than
   letting it fall back to whichever personal account is logged into gcloud
   — the same dual-account reasoning as step 4, but for the running code
   rather than the CLI:
   ```bash
   gcloud iam service-accounts create radio-comp-app \
     --display-name="radio-comp-app runtime identity"
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:radio-comp-app@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/datastore.user"
   gcloud iam service-accounts keys create ~/.config/gcloud/radio-comp-app-key.json \
     --iam-account=radio-comp-app@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```
   Keep the key file **outside this repo** (the path above is a suggestion,
   not a requirement) — `.gitignore` has a backstop pattern in case one ever
   lands inside it, but the real safeguard is not putting it there in the
   first place. If a Storage bucket gets created later per step 8, add a
   second `add-iam-policy-binding` with `roles/storage.objectAdmin` at that
   point rather than granting it up front.

Once that's done, copy `.env.example` to `.env` and fill in:

```
STORAGE_BACKEND=firestore
GCP_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/radio-comp-app-key.json
```

`google-cloud-firestore` picks up `GOOGLE_APPLICATION_CREDENTIALS` automatically
ahead of any other credential source — no code changes needed, and the app's
identity is now decoupled from whatever's logged into gcloud locally. (Skip
that line and run `gcloud auth application-default login` instead if you don't
need that isolation — fine for a single-account setup.)

## Next steps (not built yet)

1. Second aggregator adapter (theprizefinder) — same pattern as `loquax.py`.
2. Resolve the Ofcom station-directory gap above, or seed `Station` manually
   for a first tranche of local/independent stations.
3. A second direct-station monitor, ideally one that actually needs
   Playwright (a JS-heavy or bot-defended site), so the "when do we actually
   need a real browser vs. plain httpx" judgement call gets tested against a
   second real case rather than generalised from one.
4. TandCSnapshot capture + a compliance-engine first pass (spec section 4) —
   the models and EntryChannel review flags are in place for this, the
   clause-diffing logic itself isn't built yet.
5. Wire up Cloud Scheduler → Cloud Run Job now that the GCP project exists —
   see the checklist above for the remaining commands to run.
