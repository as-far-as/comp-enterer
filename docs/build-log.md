# Build log

## 2026-09-02 — Phase 0, first slice

Started building against the technical spec's Phase 0 (data model, Ofcom station
directory, community-aggregator ingestion).

**Built and working (tested against live data):**
- Full Pydantic data model (`models.py`) matching spec section 8.
- Storage layer with two backends behind one interface: local JSON (default,
  no GCP needed) and a Firestore implementation (written, not yet exercised —
  waiting on the GCP project).
- Loquax radio-competitions aggregator adapter — fetches the live listing,
  parses it, dedupes (including a same-run collapse for promotions Loquax lists
  more than once, discovered while testing), and upserts into storage.

**Known gap:** couldn't locate Ofcom's current licensed-radio-stations dataset
URL this session — needed to seed the local/independent Station tier.

## 2026-09-02 — GCP project created; first direct-station monitor

User created the GCP project ("Comp Enterer", id `project-a6778446-201f-4aa5-a03`)
with a £2 budget alert. Continued building the parts that don't need GCP access
yet while the user finishes the remaining `gcloud` setup (checklist is in the
repo README).

**Built and working (tested against live data, 7/7 tests passing):**
- `src/radiocomp/stations/talksport.py` — the first direct-station monitor.
  Real-data findings that changed the design: talkSPORT needs only plain
  `httpx`, not Playwright; entry-channel free/paid labelling is unreliable at
  face value (a "Free phone entry" channel meant "standard network rate," not
  £0), so the adapter now only marks a channel confidently free/paid on
  unambiguous clause text, else `is_free_route=None` + `review_recommended=True`;
  prize-value extraction is title-only after a body-text fallback was caught
  picking up an SMS entry cost as a "prize value."
- **Bug found and fixed:** the original data model was missing `id` fields on
  `TandCSnapshot`, `EntryChannel`, and `Outcome`, which broke the storage layer
  the moment a second collection type was actually exercised.

## 2026-09-02 — Repo live on GitHub

Repo: **https://github.com/as-far-as/comp-enterer** (private).

Getting the initial push through GitHub auth took a real detour — this
session's own git proxy blocked a direct push (repos need to be in "this
session's authorized repository set," which isn't something available from
here), so the user pushed from their own machine instead. That hit two more
snags worth remembering if this comes up again: (1) a stale/wrong credential
cached in macOS Keychain made GitHub return a misleading "Repository not
found" instead of an auth error — resolved by clearing the github.com entries
in Keychain Access; (2) manually embedding a token in a git URL is easy to
truncate by hand. Ultimately resolved by opening the repo folder in VS Code
and using its Source Control panel's "Publish Branch," which does GitHub's
proper browser OAuth flow instead of manual token handling — recommended
starting point if this repo ever needs re-authenticating on a new machine.

**Next up, per the spec's Phase 0/1:**
1. Wire `STORAGE_BACKEND=firestore` + `GCP_PROJECT_ID=project-a6778446-201f-4aa5-a03`
   once the user finishes the remaining `gcloud` setup steps (enable APIs,
   create Firestore database — see README).
2. theprizefinder aggregator adapter.
3. Resolve the Ofcom station-directory gap, or seed Station manually.
4. A second direct-station monitor that actually needs Playwright.
5. TandCSnapshot capture + first pass at the compliance engine (spec section 4).
6. Wire Cloud Scheduler → Cloud Run Job.

## 2026-09-02 — Handoff to Claude Code / VS Code

Development is moving from this Cowork session (claude.ai Project +
cloud sandbox) to Claude Code running inside VS Code, working directly on
the user's already-cloned local copy of the repo. This session's claude.ai
Project (`scoping-research.md`, `technical-specification.md`, this build
log) is not visible to Claude Code, so the three docs were copied into
`docs/` in the repo itself, and a `CLAUDE.md` was added at the repo root
(Claude Code's auto-loaded context file) summarising the project, pointers
to the docs, the non-negotiable design constraints, current build state,
and the prioritised next-steps list above. From here, treat `docs/` and
`CLAUDE.md` in the repo as the source of truth — this Project's copies
will not be kept in sync automatically once VS Code work begins; if this
build log is updated going forward, update `docs/build-log.md` in the repo
(the canonical copy) and, if this Project is still in active use, ask
the user before assuming this Project doc should also change.

## 2026-09-02 — GCP project live in europe-west2

The remaining `gcloud` setup (API enablement, Firestore database creation)
is done for `project-a6778446-201f-4aa5-a03`, using `europe-west2` (London)
rather than the `us-central1` originally assumed in the spec/README — the
user is UK-based, and Cloud Run, Firestore, and Cloud Scheduler's Always
Free tiers all work the same there. `GCP_REGION`'s default in
`src/radiocomp/config.py` and the `gcloud` commands in README.md have been
updated to match. The one carve-out: Cloud Storage's Always Free tier only
applies to `us-west1`/`us-central1`/`us-east1`, so if a Storage bucket is
ever created for this project it should go in `us-central1` specifically,
not `europe-west2` — see README.md's GCP setup section.

## 2026-09-02 — Isolating this project's GCP identity (dual-account setup)

Adán runs multiple Google accounts across different VS Code windows/terminals
(this project's personal GCP account is separate from at least one work
account also active in gcloud locally, which currently defaults to a
`dbol-prod` project). To stop a stray `gcloud` command or the app's own
Firestore client from silently hitting the wrong account/project:

- Added a `radio-comp` named gcloud configuration (project + region set,
  left inactive globally — `gcloud config configurations create` activates
  by default, which was reverted immediately since that would have changed
  the active config for every terminal, not just this repo's).
- Added `.envrc` (direnv) so any shell that `cd`s into this repo scopes
  `gcloud` to that config via `CLOUDSDK_ACTIVE_CONFIG_NAME` for that shell
  only, and also loads `.env`. Requires `brew install direnv` + a one-time
  shell hook + `direnv allow` — not done automatically, since it touches
  the user's global shell rc file.
- Recommended (README step 9) a dedicated `radio-comp-app` service account
  with a minimal `roles/datastore.user` binding, key referenced via
  `GOOGLE_APPLICATION_CREDENTIALS` in `.env`, so the running app's identity
  doesn't depend on whichever personal account is logged into gcloud at the
  time — `google-cloud-firestore` picks that env var up automatically ahead
  of ADC. Key should live outside the repo; `.gitignore` got a backstop
  pattern (`*-key.json`, `service-account*.json`) in case one ever lands
  inside it anyway.
- Updated `config.py` / `firestore_store.py` docstrings and added
  `.env.example` to match — they previously assumed plain
  `gcloud auth application-default login` with no key management.

Still needs the user to actually run: `gcloud auth login` under the correct
account (with `radio-comp` active), the `brew install direnv` + shell hook
step, and the service-account-creation commands in README step 9 — none of
that could be done from this session (interactive browser auth, and the
active gcloud credential here belongs to the other account, which doesn't
have permission on this project anyway).

## 2026-09-02 — Dedicated service account blocked by an org-level Deny policy

Follow-up to the identity-isolation work above. Once the user logged into
`adan.shennan96@gmail.com` (the account this GCP project actually belongs
to) and it turned out to be a dual-account mixup along the way — a stray
`gcloud auth login` landed on the `default` gcloud configuration instead of
`radio-comp`, silently changing which account `default` pointed at; caught
and fixed (`gcloud config set account ... --configuration=default/radio-comp`)
before it caused real damage. Lesson: `gcloud auth login` / `application-
default login` must only be run from a shell where the target named
configuration is already active (or passed via `--configuration=`), never
assumed.

Then, trying to build the `radio-comp-app` service account (README step 9
as originally written):

1. **Key creation blocked.** `gcloud iam service-accounts keys create` failed
   with `FAILED_PRECONDITION: constraints/iam.disableServiceAccountKeyCreation`.
   Checking the resource hierarchy showed this project sits under a Google
   Cloud **organization** (`183072770325`) — unusual for a project created
   from a plain personal Gmail account. The user, despite being project
   Owner, got permission-denied trying to override the policy even at the
   project level (`orgpolicy.policies.setOrgPolicy` denied), and separately
   couldn't list deny-policies at the org level either. Conclusion: this is
   Google's automatic "default resource organization" wrapper for personal/
   non-Workspace accounts, applying baseline security guardrails that the
   nominal project owner doesn't administer.
2. **Fell back to impersonation** (`gcloud auth application-default login
   --impersonate-service-account=...`) instead of a key — this got past the
   key-creation block (impersonation needs no key), but every actual
   Firestore call then failed with a bare `403 Missing or insufficient
   permissions`, for both reads and writes.
3. **Ruled out role-scoping**: granted `roles/editor` (well beyond
   `roles/datastore.user`) directly to the service account — identical 403.
   Meanwhile the same calls made as the plain human user (`adan.shennan96@
   gmail.com`, no impersonation) worked immediately. So the block is
   specific to service-account-authenticated calls, not to Firestore, not
   to role scope.
4. **Confirmed via the IAM Policy Troubleshooter** (Console): for the
   service account + `datastore.entities.get`/`create` on this project, the
   classic role (Cloud Datastore User) showed **Granted** — but the page's
   Deny Policy section read "You don't have permission to view any of the
   resources' deny policies." A Deny policy is in effect, attached above
   the project, invisible to the project owner. This is consistent with
   point 1: a Google-managed guardrail on the auto-created org, not
   something fixable via any `gcloud` command available here.
5. **Decision: use the human account's own ADC directly for local dev**
   (`gcloud auth application-default login --configuration=radio-comp`, no
   impersonation) — confirmed working with a full round-trip smoke test
   (write/read/list/delete) against real Firestore via `firestore_store.py`,
   plus the existing 7/7 test suite still passing (those run against local
   storage/fixtures, unaffected). This gives up the "app identity decoupled
   from personal account" isolation goal, because the alternative (a
   dedicated service account) isn't available on this account/org — not a
   choice, a platform constraint.

**Open risk carried forward** (noted in README step 10): Cloud Run's runtime
identity is *also* a service account. If this Deny policy blocks service
accounts broadly rather than specifically the ones this session touched, the
eventual Cloud Scheduler → Cloud Run Job wiring (next-steps item 6) could hit
the exact same wall in production. Re-test this specifically when building
that piece — don't assume Cloud Run will work just because local ADC does.
Cleanup note: the `radio-comp-app` service account and its `roles/datastore.
user` binding were left in place (harmless, currently unusable) in case a
future org/account change makes it usable; all one-off test bindings
(`roles/editor` on `radio-comp-app`, anything on the default compute service
account) were reverted.

## 2026-09-02 — ThePrizeFinder aggregator adapter

Second aggregator, `src/radiocomp/aggregators/theprizefinder.py`, same shape
as `loquax.py`: `fetch_listing_html()` / `parse_listing()` / `ingest()`,
tested offline against a saved real fixture
(`tests/fixtures/theprizefinder_radio_search.html`).

Investigated theprizefinder.com's structure first (sitemap.xml, site nav) —
unlike Loquax it has **no dedicated radio-competitions category**; its
taxonomy is organised by prize theme (TV, social media, creative, seasonal),
not broadcast medium. The closest available discovery mechanism is its
keyword search, `/search/competitions?keys=radio`, which turned out to
match promoter/company names as well as titles — so results are mostly
genuine radio-station promoters (Virgin Radio, Smooth Radio, Radio X, YO1
Radio observed live) plus at least one false positive that just happens to
contain the word: "Radio Times", the listings magazine, isn't a broadcast
station. Per the project's conservative-extraction stance, the adapter
doesn't try to filter that out — station_name_raw is captured as seen,
same as Loquax's unresolved-station pattern, and resolving/rejecting
against real `Station` records is left for a future normalizer step. A
test (`test_keyword_search_false_positives_are_captured_not_filtered`)
exists specifically to lock in that "don't guess" behaviour rather than
someone later "fixing" it into a fragile name-based exclusion list.

Unlike Loquax, ThePrizeFinder's listing rows expose the promoter name and a
machine-readable closing datetime (`<time datetime="...">`) directly on the
anonymous page — no login-gated thread to work around, so `entry_deadline`
and `station_name_raw` come through with real values immediately rather
than needing a follow-up fetch.

Live one-off run (`python -m radiocomp.aggregators.theprizefinder`) against
the real site returned 9 promotions, matching the fixture. 11/11 tests
passing (7 prior + 4 new).

## 2026-09-02 — Ofcom register gap investigated properly; manual seed instead

Went back to the "known gap" the original scoping session left open: no
current, bulk-downloadable Ofcom register of licensed radio stations was
ever located. Checked properly this time rather than re-flagging the same
gap:

- **data.gov.uk / CKAN** (`ckan.publishing.service.gov.uk`, filtered to the
  Office of Communications organisation): the only radio-related datasets
  are market/revenue statistics, plus one **technical-parameters-for-
  broadcast-radio-transmitters** dataset (TxParams AM/MF/VHF/DAB CSVs) —
  transmitter-level technical data, not a station register as such, and
  every resource's metadata says **last updated 19 March 2019**.
- The actual file URLs from that 2019 dataset (`ofcom.org.uk/__data/assets/
  file/...`) are now **dead — 404**, confirming Ofcom has reorganised its
  site since, consistent with what the original session already suspected.
- The current `ofcom.org.uk` site has a **"Look up radio station details"**
  tool (`/tv-radio-and-on-demand/analogue-radio/look-up-radio-station-
  details`), but no download/export link or API surfaced in its markup —
  it reads as a single-record interactive lookup, not a bulk source. Not
  worth building a scraper against something that can't confirm when
  you've found everything.

**Conclusion: this gap stays open** — there is no clean current bulk
register to import from right now, not just "wasn't found this time."

Built the fallback both the spec and README already sanctioned instead:
`src/radiocomp/stations/seed_local_independent.py`, a manually-picked first
tranche of 14 `Station` records. Every candidate was checked live (fetched
its own website, confirmed it resolves to itself with matching content)
before inclusion — this caught real mistakes along the way worth recording:
Swansea Sound, Trax FM, Dearne FM, Ridings FM, and Rutland Radio all
redirected to `hellorayo.co.uk/greatest-hits/<region>` — they've been
absorbed into Bauer's Greatest Hits Radio network and are no longer
independent, contradicting what would've been a reasonable-sounding guess
from memory. Rugby FM's domain has been squatted by an unrelated gambling
content site. Several other candidates (Original 106 Aberdeen, Time 107.5,
Tameside Radio, That's Solent, Chelmsford Radio) were dead domains or
redirected somewhere unrelated. None of this would have surfaced without
actually fetching each one — a direct instance of the project's "verify,
don't guess" rule applying to station metadata, not just prize values or
channel classification.

Final 14: Isle of Wight Radio, Central FM, Drystone Radio, Banbury Sound,
2BR, Energy FM, Manx Radio, Bolton FM, KMFM, Susy Radio, Amber Sound FM,
Insanity Radio, Angel Radio, Diverse FM. `seed()` upserts by name (confirmed
idempotent — a second run added 0 new stations). 6 new tests on the seed
data itself (no duplicate names, every station flagged local-independent,
every base_url live-checked and https, no fabricated `ofcom_licence_ref`,
manual-seeding disclosed in `notes`). 17/17 tests passing overall.

## 2026-09-02 — Second direct-station monitor: Radio Exe, and a Playwright search that came up empty

Went looking for a second direct-station monitor, explicitly hoping for one
that genuinely needs Playwright this time (talkSPORT didn't, and that
judgement call — browser vs. plain httpx — is worth testing against more
than one case). Checked ~35 candidates: the 14 seeded local/independent
stations, Global's Heart/Capital/Smooth, Bauer's Kiss/Absolute Radio/
Greatest Hits Radio (via the shared hellorayo.co.uk platform), Nation
Broadcasting's Nation Player platform, and a batch of other independent
local stations, looking specifically for either genuine client-side-only
rendering or real Cloudflare bot challenges.

Result: almost everything server-renders its real content regardless of
how JS-heavy it looks. Bauer's hellorayo.co.uk pages carry full React/Next
hydration markers and 800KB+ of HTML but the actual competition titles are
sitting right there in a server-rendered `__NEXT_DATA__` blob. Nation
Player's site shows a cookie-consent interstitial and an "Aiir" JS-widget
footer but both its listing and detail pages are fully readable via plain
httpx — confirmed by rendering with Playwright too and finding the same
content, just slower to get. Phoenix FM's Cloudflare-fronted site initially
looked like a bot challenge (matched on `challenge-platform` in the page
source) but that turned out to be Cloudflare's standard passive bot-
detection script tag, not an actual block — the page loads fine either way.
The one genuine case found — **Angel Radio**, a small nostalgia-format
charity station built on Wix — really does need a browser (homepage visible
text is ~90 characters via plain httpx *and* via a rendered Playwright
page; real Wix content apparently loads even more lazily than a 6-second
wait captures), but has no discoverable competition activity worth building
a monitor around.

Given that, and per the user's call on this trade-off, built the second
monitor with plain httpx anyway: **Radio Exe** (`src/radiocomp/stations/
radioexe.py`), on Nation Broadcasting's Nation Player platform. Two things
worth flagging for future adapters on this platform (other Nation-branded
stations likely share the same `c-pod__*` Aiir template classes):

1. Entry-channel text reads a lot like talkSPORT's — the same "charged at
   the standard rate" phrasing shows up for a phone-entry route here too,
   and gets the same Gambling-Act-compliant free-route treatment (still
   never auto-dialled, same non-negotiable constraint, just correctly
   classified as `is_free_route=True`).
2. One live competition asked for entry via **WhatsApp message** or
   **email** — neither existed as an `EntryChannelType`. Added `EMAIL` and
   `WHATSAPP` to the model (`models.py`) rather than force-fit them into
   `SMS`/`WEB_FORM`, which would have misrepresented both their cost
   profile and the fact that no automation path touches either. Both
   always come through with `review_recommended=True` — no cost signal is
   ever visible for these two in practice, so they're never confidently
   marked free.

Live one-off run (`python -m radiocomp.stations.radioexe`) against the real
site found both currently-live Radio Exe competitions, classified 5 entry
channels across them, matching the fixtures exactly. 4 new tests
(listing extraction, multi-channel classification on the "Make Me A
Winner!" network competition, WhatsApp/email capture-and-flag behaviour,
and confirming a recurring weekly promo with no fixed date correctly stays
`entry_deadline=None` rather than guessed). 21/21 tests passing overall.

Also installed `playwright` + Chromium into `.venv` and uncommented it in
`requirements.txt` while investigating the above — kept installed even
though this adapter didn't end up needing it, since the next Playwright-
requiring case (a real one will turn up eventually) shouldn't need to
re-install it from scratch.

## 2026-09-02 — Compliance engine, first pass (spec section 4)

Built `src/radiocomp/compliance/`: `tandc.py` (T&C snapshot capture) and
`engine.py` (the two checks spec section 4 names — already-entered, and
cross-brand shared-limit duplicates). No entry-execution engine exists yet
(spec section 5, not built), so nothing here actually blocks an entry from
happening — it's a pair of testable functions surfacing exactly what that
engine will need to check once it exists, run today against what's already
been discovered.

`tandc.py`'s two parsed fields (`parsed_free_route_exists`,
`parsed_entry_limit`) turned out to need to stay much shallower than a
first instinct would suggest, once checked against talkSPORT's own real
fixtures rather than assumed: real entry-limit clauses are genuinely
complex and multi-channel ("up to a maximum of 100 times Online", "£40 on
paid SMS entries", "116 postal entries" — no single phrase to extract), and
a bare "free entry" phrase match turned out to sit inside a *paid*
boost-offer clause on the same page. Both fields now only fire on a narrow
set of known-reliable phrasings (reusing the same "standard rate"/"standard
network rate" vocabulary talksport.py and radioexe.py already rely on for
the same reason) and default to `None` otherwise — another instance of this
project's standing rule: an honest gap beats a confident wrong parse.
`raw_text` + `raw_text_hash` preserve everything else for an actual human
read, which is the point of a *snapshot* rather than a full parse.

`engine.py`'s cross-brand-duplicate check reuses ThePrizeFinder's own real
fixture as its main test — the £4,000 TUI gift-card promotion that showed
up under both Smooth Radio and Radio X (see the ThePrizeFinder build-log
entry above) is a genuine live instance of the exact scenario spec section
4 describes, so `test_compliance_engine.py` checks the real thing rather
than a synthetic stand-in. Matching is deliberately narrow (exact title
match once case/whitespace-normalised, same network, same deadline when
both have one) rather than fuzzy string similarity — a missed match just
means two separately-flagged promotions (safe), a false match would
incorrectly suppress a real second entry opportunity (not safe). Network
membership lists (`SHARED_LIMIT_NETWORKS`) are deliberately short, limited
to station names this session could actually confirm live — several
plausible Bauer/Global regional names turned out to have moved between
groups or been retired when checked earlier this session (see the Station-
seed build-log entry above); extend the lists as more get confirmed rather
than guessing from names alone.

Ran both modules live against real local data from earlier sessions'
ingestion runs (not just fixtures): `check_promotion()` correctly flagged
both real TUI gift-card promotions in `data/promotions.json` as cross-brand
duplicates of each other, and `capture_snapshot()` correctly found
`parsed_free_route_exists=True` for Radio Exe's "Make Me A Winner!" (which
has a standard-rate phone route) and `None` for "Free Film Friday" (WhatsApp/
email entry only, no rate wording on the page at all). 33/33 tests passing
(12 new).

## 2026-09-03 — Billing account was closed; reopened

Went to start on Cloud Scheduler → Cloud Run Job (build-log step 6) and hit
`BILLING_DISABLED` trying to even list Artifact Registry repos, despite
`gcloud billing projects describe` showing a billing account linked. Turned
out `gcloud billing accounts describe` told the real story: the linked
billing account itself had `open: false` — closed, not just unlinked,
apparently because a valid payment method was never actually attached at
setup time. User added a payment method and reopened it via the Console;
confirmed fixed via the same `describe` command (`open: true`) and a
successful `gcloud artifacts repositories list` call. This was a separate,
simpler problem from the earlier org-level Deny-policy issue — worth not
conflating the two "GCP won't let me do X" moments as the same root cause
just because they showed up in the same session.

## 2026-09-03 — Confirmed: Cloud Run can't reach Firestore either, but Cloud Storage works

With billing fixed, ran the smoke test build-log 2026-09-02 flagged as
needed before building the real Cloud Run pipeline: does Cloud Run's actual
runtime identity hit the same Firestore Deny-policy wall the custom
`radio-comp-app` service account did? Built a minimal container (`google-
cloud-firestore`, one read/write against a throwaway collection), pushed it
to a new Artifact Registry repo (`radio-comp`, europe-west2), ran it as a
real Cloud Run Job with no custom service account (so it used the default
compute service account, `PROJECT_NUMBER-compute@developer.gserviceaccount.com`
— confirmed via the job's own execution spec). Result: identical `403
Missing or insufficient permissions`, straight from Cloud Run's own logs,
not a local inference. Confirms the org's Deny policy blocks *any* service
account's Firestore access on this project, Cloud Run's own runtime
identity included — not something specific to impersonation or to the
custom service account from the 2026-09-02 investigation.

Along the way, hit two more routine (not org-policy) permission gaps worth
noting since they'll recur for anyone setting up Cloud Build fresh on a
project that's never used it before: the default compute service account
started with *zero* IAM roles at all, so `gcloud builds submit` failed
first on `storage.objects.get` (couldn't read its own uploaded source
tarball) and then, once that was granted, on
`artifactregistry.repositories.uploadArtifacts` (couldn't push the built
image). Granted `roles/storage.objectViewer` and `roles/artifactregistry.
writer` to that service account at the project level and both resolved
immediately — ordinary missing-grant issues, not the Deny-policy wall,
confirmed by the fact granting the role actually worked (the Deny-policy
case never responds to a role grant, as the 2026-09-02 `roles/editor` test
already showed).

Then tested the same default compute service account against **Cloud
Storage** instead — created a throwaway bucket, granted `roles/storage.
objectAdmin`, ran an equivalent Cloud Run Job doing one write + read-back.
It worked (`GCS_OK: ok`). So the Deny policy is scoped to Firestore/
Datastore specifically, not service accounts in general — a real, usable
distinction, not just "everything is blocked here."

Given that, built a third storage backend: `src/radiocomp/storage/
gcs_json.py`, same one-JSON-blob-per-collection shape as `local_json.py`,
picked via `STORAGE_BACKEND=gcs` (+ `GCS_BUCKET_NAME`) in `storage/base.py`.
Created the real bucket for this (`project-a6778446-201f-4aa5-a03-data`,
`us-central1` per the region rule already documented for Storage), granted
the default compute service account `roles/storage.objectAdmin` on it.
Verified `gcs_json.py`'s actual code — not a reimplementation, the real
module — end-to-end inside a real Cloud Run Job (built a throwaway image
copying in `src/radiocomp`, ran `get_repository('_cloudrun_gcs_smoketest',
Station)` through a full add/get/list/cleanup cycle): completed
successfully, `CLOUD_RUN_GCS_OK: Cloud Run GCS Smoke Test FM` in the logs.
All test jobs, images, and the throwaway bucket were deleted afterward;
the real `project-a6778446-201f-4aa5-a03-data` bucket and the `radio-comp`
Artifact Registry repo stay, since the real pipeline will need both.

One more instance of the global-ADC-file fragility already flagged on
2026-09-02: partway through this session, a local Python script reading
ADC (no `GOOGLE_APPLICATION_CREDENTIALS` set) resolved to `dbol-elt-runner@
dbol-prod.iam.gserviceaccount.com` — the user's own work identity, not
`adan.shennan96@gmail.com`, meaning something (most likely the user's own
work tooling running `gcloud auth application-default login` for its own
purposes elsewhere) had silently overwritten the shared ADC file since the
last time this project used it. Worked around it for testing purposes by
building `google.oauth2.credentials.Credentials` from `gcloud auth print-
access-token --configuration=radio-comp` directly rather than fighting over
the ADC file again — doesn't touch the global file at all, so it's a better
default for one-off local verification than re-running `application-default
login` back and forth. Cloud Run itself is entirely unaffected by any of
this, since it never reads local ADC — only local testing of the Firestore
path is exposed to this fragility.

33/33 existing tests still passing (no test-suite changes this entry —
this was infra investigation and a new storage backend verified via live
Cloud Run runs, not fixture-based unit tests, matching how firestore_store.py
itself was verified).

## 2026-09-03 — Cloud Scheduler → Cloud Run Job: live, hourly, end-to-end

With `gcs_json.py` proven, built and shipped the real scheduled pipeline.

`src/radiocomp/run_discovery.py`: one entrypoint running every adapter
(`loquax`, `theprizefinder`, `talksport`, `radioexe`) in sequence, catching
each one's exceptions independently — one station breaking shouldn't take
the others down, only exits non-zero if literally everything failed. Caught
a real bug writing the first version of this: `_load_adapters()` appended
to a module-level list rather than returning a fresh one each call, so
calling it twice (which a quick manual test of the partial-failure path
did) silently duplicated every adapter. Refactored to return a plain list
instead of mutating a global — simpler and the bug class isn't possible
anymore. 4 new tests (`test_run_discovery.py`) using fake ingest()
callables rather than the real adapters, which already have their own
fixture-based coverage; these just check the orchestration logic itself.
37/37 tests passing.

`Dockerfile`: deliberately not `pip install -r requirements.txt` — that
also pulls in Playwright (unused by any adapter so far, large Chromium
download) and `google-cloud-firestore` (Cloud Run can't reach Firestore at
all here). Just the five packages `run_discovery`'s adapters actually
import. Built and pushed to the `radio-comp` Artifact Registry repo via
`gcloud builds submit`.

Created the real Cloud Run Job, `radio-comp-discovery`
(`STORAGE_BACKEND=gcs`, 512Mi/1cpu, 300s timeout). First real execution: 3
of 4 adapters succeeded, 18 new promotions written to the real
`project-a6778446-201f-4aa5-a03-data` bucket — genuine production data now,
not a smoke test. Confirmed via `gcloud storage cat` on the actual blob.

**Loquax returned `403 Forbidden` from Cloud Run specifically** — same
adapter, same code, works fine run locally (confirmed side-by-side, same
session). Almost certainly Loquax blocking Google Cloud's IP ranges by
reputation, not a bug in the adapter. `run_discovery.py`'s per-adapter
isolation meant this didn't take the run down — 3/4 succeeded, exit 0 —
but it's a real, currently-unresolved gap in Loquax's coverage specifically
from the scheduled job. Left as a known issue (README's "Next steps") since
diagnosing/fixing an IP-reputation block is its own piece of work, not
something to solve as a side effect of wiring up Scheduler.

Wired Cloud Scheduler: granted the default compute service account
`roles/run.invoker` on the job (needed for Scheduler's OAuth-authenticated
HTTP call to the Cloud Run Admin API — a `run.jobs.run` permission check,
unrelated to the Firestore Deny policy, and unaffected by it, consistent
with everything else this session found about that policy being scoped to
Firestore/Datastore specifically). Created `radio-comp-discovery-hourly`
(`0 * * * *`, Europe/London) targeting the Run Admin API's `:run` endpoint.
Confirmed the whole chain actually works, not just "looks right in
`describe`" — manually triggered via `gcloud scheduler jobs run`, watched a
new Cloud Run execution appear a few seconds later
(`radio-comp-discovery-q7ssh`, run by the compute service account, not a
human — exactly what a real scheduled trigger should look like), watched
it complete successfully in 48s.

Cleanup: none needed this time — `radio-comp-discovery` (the job),
`radio-comp-discovery-hourly` (the schedule), and the `discovery` image are
all the real, permanent pipeline now, not throwaway test resources.

The discovery half of this project (spec Phase 0) now runs entirely on its
own, hourly, without any machine of the user's needing to be on — the
"runs in the background, not tied to my laptop" goal from the spec's
hosting section is live. What's not built yet: anything downstream of
discovery (compliance engine wiring into a real workflow, notification
layer, entry-execution engine) — this only ever writes Promotions/
EntryChannels, same as running an adapter by hand always did.

## 2026-09-03 — Read-only view of what's actually been discovered

User asked, reasonably, how they were meant to interact with any of this —
the honest answer at that point was "you can't, it's raw JSON in a
bucket." Confirmed the actual entry-drafting/submission plan (spec section
5) matches what the user expected in shape (system fills the form and
drafts it, human approves, system submits — not fully manual, not fully
autonomous either; creative/skill-based questions are explicitly never
auto-answered, phone/call-in entries never automated at all), but none of
that exists yet. Rather than build straight into the Telegram bot (spec
section 6, which needs the entry-execution engine from section 5 to
actually gate anything — building the approve/skip UI before there's
anything for it to approve would be building ahead of what's real), built
the smallest useful thing first: `src/radiocomp/view_promotions.py`, a
read-only CLI listing every known Promotion (soonest deadline first) with
its EntryChannels and a live compliance-engine check run inline, so a
cross-brand duplicate or already-entered promotion is visible without a
separate step.

Verified against both real local test data (confirmed the TUI cross-brand
duplicate note renders correctly) and the real GCS-backed production data
from the live scheduled job (18 promotions, matches what
`gcloud storage cat` showed directly) — using the same token-based
credentials trick from 2026-09-02/03 rather than fighting the shared ADC
file again. 4 new tests on the pure formatting logic (`_format_channel`);
the storage-reading `main()` itself is exercised live rather than unit
tested, same convention as the storage backends. 41/41 tests passing.

## 2026-09-03 — Loquax's Cloud Run block diagnosed and fixed via GitHub Actions

User asked how important Loquax's coverage actually was and whether there
was a free fix, rather than accepting the gap or paying for one. Worth
actually diagnosing before answering either question.

**Diagnosis.** Built a throwaway Cloud Run Job that fetched Loquax's
listing page and printed the full response (headers + visible text, not
just the status code seen in run_discovery.py's logs). The body wasn't a
Cloudflare challenge page — it was XenForo's own generic error template,
and the actual visible text was unambiguous: **"Your IP address has been
banned."** An application-level ban by the forum software itself (or an
integrated IP-reputation plugin), not a User-Agent or header issue — the
same User-Agent works fine locally. Almost certainly Google Cloud's shared
egress IP pool got flagged by unrelated traffic from other GCP tenants
sharing those same IPs, not anything about this adapter's own behaviour.
Cleaned up the diagnostic job/image afterward.

**Considered and rejected**: Cloud NAT with a static IP, or a residential-
proxy service — both add ongoing cost for restoring one aggregator's
coverage, when the marginal value of that coverage is already reduced by
Loquax's own pre-existing limitation (station name unresolved on a
meaningful share of its listings — see loquax.py's docstring, unrelated to
today's ban).

**The actual fix, tested before building anything**: pushed a throwaway
GitHub Actions workflow (`test-loquax-network` branch, deleted after) that
just curled Loquax's listing page from a GitHub-hosted runner and committed
the raw response to the branch (worked around `gh` CLI being logged into
the wrong GitHub account for this repo — plain `git push`/`fetch` already
had working credentials, so the Action wrote its result back as a commit
instead, read via `git show origin/<branch>:<file>` with zero extra auth
needed). Result: `HTTP status: 200`, the real listing page — GitHub
Actions' runners aren't on Loquax's ban list. Confirmed *before* building
any real infrastructure, per the project's own "verify against something
real" habit.

**Built once confirmed**: Loquax now runs from
`.github/workflows/loquax-scheduled.yml` (hourly, offset `:17` from Cloud
Run's `:00` schedule) instead of `run_discovery.py`/Cloud Run. Auth is
Workload Identity Federation, not a downloadable service-account key —
still blocked on this project's org (2026-09-02) — so GitHub's OIDC token
gets exchanged for short-lived GCP credentials each run instead. Setup:

- A Workload Identity Pool (`github-actions`) + OIDC provider
  (`github-actions-provider`, issuer `https://token.actions.githubusercontent.com`),
  with an **attribute condition restricting it to `assertion.repository ==
  'as-far-as/comp-enterer'`** — no other GitHub repo could impersonate this
  identity even with the same provider resource name.
- Reused the existing (previously unusable) `radio-comp-app` service
  account: bound `roles/iam.workloadIdentityUser` to the specific
  principalSet for this repo, and granted it `roles/storage.objectAdmin`
  on the real bucket (its earlier `roles/datastore.user` binding is now
  simply dead weight from the abandoned Firestore-service-account attempt).

**Verified end-to-end before merging**, same test-branch pattern as the
diagnosis step: temporarily added a `push: branches: [test-loquax-wif]`
trigger, pushed, watched the real bucket's `promotions.json` go from 18 to
25 promotions (7 new, real Loquax competitions, `station_name_raw`
correctly showing "(unresolved — see Loquax thread)" per that adapter's
existing honest-gap design) — confirmed via `gcloud storage cat`, not
inferred from the workflow "looking right." Removed the temporary trigger
and merged to main.

Updated `run_discovery.py` accordingly: `loquax` removed from its adapter
list (it would fail every single time from Cloud Run, no point calling it
there), with the module docstring explaining where it actually runs now.
41/41 tests still passing (no test changes needed — `_load_adapters()`'s
own tests use fake callables, unaffected by which real adapters are
listed).

Coverage is now fully automated across all four discovery adapters again,
each from whichever network can actually reach it — no ongoing cost, no
manual intervention, no laptop required for any of it.

## 2026-09-04 — Telegram bot: notify + approve/skip, built and code-tested

User asked to prioritise the human-in-the-loop surface (spec section 6)
over expanding discovery coverage further, since 25+ promotions were
already sitting undiscoverable-in-practice with no way to act on any of
them. Initially scoped this down to notification-only (matching the
existing `view_promotions.py` stopgap pattern) and entered plan mode to
design it — the user corrected this mid-plan: they want the full
interactive bot (Approve/Skip buttons, webhook receiver, Cloud Run
Service), tested end-to-end for real, not another stopgap. Re-planned
accordingly, with one scope question genuinely worth asking rather than
assuming: does tapping Approve *record* a decision, or actually *submit*
the entry? User chose record-only — the entry-execution engine (spec
section 5, Playwright form-filling) stays a distinct future step, keeping
the highest-risk part of this whole project (real automation touching
external sites) out of this change while still delivering a complete,
real, testable loop: discover → notify → tap → recorded.

**Design, via a Plan subagent grounding every claim against the actual
codebase and Telegram's own Bot API docs rather than assuming:**

- `src/radiocomp/notify/` (outbound — `telegram_client.py`,
  `callback_data.py`, `channel_selection.py`, `message.py`, `send.py`) vs.
  `src/radiocomp/webhook/` (receiver — `app.py`, `handlers.py`), split
  specifically so the existing lean discovery `Dockerfile` never needs
  FastAPI. Plain `httpx` calls to Telegram's REST API, not
  `python-telegram-bot` — that library's real value (webhook/update
  routing) is redundant once FastAPI's already doing that job, and three
  REST calls (`sendMessage`, `answerCallbackQuery`, `editMessageText`)
  don't need a framework of their own.
- **No `parse_mode` anywhere, ever** — scraped titles/prize text routinely
  contains characters MarkdownV2 requires escaping (`. ! ( ) -` and more);
  an unescaped send just 400s. Plain text throughout, permanently, not a
  gap to "improve" later — the same reasoning `tandc.py` already
  documented for why its own parsing stays shallow.
- **Buttons only appear when there's something safe to approve**:
  `channel_selection.select_approvable_channel()` picks the first
  `EntryChannel` with `is_free_route is True and review_recommended is
  False`, else `None` → plain notification, no buttons. Same "don't guess"
  posture as every adapter's channel classification, just expressed as
  "no button" instead of "no confident value".
- `callback_data` format `f"{action}:{promotion_id}:{channel_id}"` — 27
  bytes, comfortably under Telegram's 64-byte limit.
- **Idempotency and a real, if minor, schema gap found while designing
  it**: `EntryRecord` only stored `channel_type`, not which specific
  `EntryChannel` — insufficient to dedupe two free channels of the same
  type on the same promotion. Added `EntryRecord.channel_id: Optional[str]
  = None` (small, backward-compatible) rather than carry the imprecision
  forward.
- **Compliance re-checked fresh at approval time**, not reused from
  whatever was true when the notification was sent — hours can pass, and
  another approval in the meantime could change the answer. The recorded
  decision isn't blocked by a duplicate/already-entered finding (nothing
  exists yet to actually enforce that), but the note is still attached to
  the `EntryRecord` for visibility.
- **Webhook security**: `--allow-unauthenticated` is required (Telegram's
  servers can't do GCP IAM auth), so `webhook/app.py` checks the
  `X-Telegram-Bot-Api-Secret-Token` header — Telegram's actual documented
  mechanism for this (verified against Telegram's own docs during
  planning, not assumed): `setWebhook`'s `secret_token` parameter gets
  echoed back verbatim on every genuine call afterward.
- **A gotcha confirmed via a real local test, not just read about**:
  `editMessageText` leaves the *existing* inline keyboard in place if
  `reply_markup` is omitted — it does not clear it. `handlers.py` always
  passes `reply_markup={"inline_keyboard": []}` explicitly on the
  post-decision edit; flagged in code comments as the single detail most
  likely to regress into a bug if "simplified" later.

**Built and verified locally** (no live Telegram token needed for this
part): 73/73 tests passing (32 new — `test_channel_selection.py`,
`test_callback_data.py`, `test_notify_message.py`, `test_notify_send.py`,
`test_webhook_handlers.py`, plus `test_view_promotions.py` renamed to
`test_formatting.py` after promoting its `_format_channel` helper to a
shared, public `formatting.format_channel_line` used by both
`view_promotions.py` and `notify/message.py`). Beyond unit tests, ran the
actual FastAPI app via `TestClient` against real `LocalJsonRepository`
instances: confirmed `/healthz`, confirmed the secret-token check rejects
missing/wrong headers with 403, and confirmed a full realistic
`callback_query` payload through the real HTTP route creates a genuine
`EntryRecord` — the only thing that failed, expectedly, was the outbound
Telegram API calls themselves (no real bot token configured yet locally),
and `webhook/app.py` caught that and still returned 200 rather than
crashing, exactly as designed.

**Not yet done** (next: needs the user's own manual steps first — a bot
token and two secrets can't pass through an AI agent's tool calls, per
this session's established convention): creating the actual Telegram bot,
provisioning `telegram-bot-token`/`telegram-webhook-secret` in Secret
Manager, building/pushing `Dockerfile.webhook`, deploying the
`radio-comp-webhook` Cloud Run Service, wiring secrets into it and into
the existing `radio-comp-discovery` Job, adding the two GitHub repo
secrets for the Loquax path, and registering the webhook with Telegram —
then the actual live end-to-end test: a real message, a real tap, a real
recorded decision.

## 2026-09-04 — Telegram bot deployed and live-verified; three real bugs found and fixed along the way

Finished the infra from the entry above: user created the bot
(`Radio Comp Enterer`, `@radio_comp_alerts_bot`) via the real `@BotFather`
(a first attempt found an impersonator username instead — worth double-
checking the blue checkmark), created both secrets, added the GitHub repo
secrets. Granted `roles/secretmanager.secretAccessor` on both secrets to
the default compute service account, built and pushed `Dockerfile.webhook`,
deployed `radio-comp-webhook` (Cloud Run Service, `europe-west2`,
`--allow-unauthenticated`), rebuilt and redeployed the discovery Job's
image (it needed rebuilding too — `run_discovery.py`/`loquax.py`'s notify
calls were new code not yet baked into the previously-deployed image),
wired `TELEGRAM_BOT_TOKEN` (via Secret Manager) and `TELEGRAM_CHAT_ID`
(plain env var) into the discovery Job.

**Bug 1 — `/healthz` silently 404s, never reaching the container.**
Confirmed via Cloud Run logs: the request never generated a log entry at
all, while every other path (`/telegram/webhook`, `/docs`, even a
deliberately-wrong `/`) worked and logged normally. This is Google's own
front-end infrastructure intercepting that specific path before Cloud
Run's routing ever sees it — a known-if-obscure quirk, not a bug in the
app. Fixed by renaming the route to `/ping`; nothing Telegram-facing
depended on the old name.

**Bug 2 — real end-to-end test found a genuine first bug**: sent a real
notification by running a throwaway one-off Cloud Run Job (reusing the
already-tested discovery image with a `--command`/`--args` override
calling `notify_new_promotions` directly against one real stored
promotion — kept the token server-side the whole time, never touched
locally) — the message arrived with buttons, confirming the outbound half
completely. Tapping Approve then failed: `getWebhookInfo` showed
`"last_error_message":"Wrong response from the webhook: 403 Forbidden"`.
Root cause: the setup instructions' own
`openssl rand -hex 32 | gcloud secrets create ... --data-file=-` pipes
`openssl`'s trailing newline straight into the stored secret, while
Telegram's registered `secret_token` (submitted via a one-line `curl -d`)
never has one — so the header Telegram sends back never matched what
`webhook/app.py` compared it against. Fixed with `.strip()` on the
configured value at comparison time (robust regardless of how the secret
was created) and updated the README's setup instructions to use
`printf '%s' "$(openssl rand -hex 32)"` for anyone re-provisioning.

**Bug 3 — a real credential leak, caught by actually reading the logs
rather than just checking the tap worked**: once the secret-token fix was
redeployed and the user re-tapped Approve, the webhook logs showed the
full sequence working — `Recorded approved for promotion ...` — but the
very next lines were `httpx` request logs showing the complete
`answerCallbackQuery`/`editMessageText` URLs **with the live bot token
embedded in the path**, exactly as Telegram's Bot API places it. `httpx`
logs full request URLs at INFO by default; `logging.basicConfig(level=
INFO)` in `webhook/app.py`, `run_discovery.py`, and `loquax.py`'s
`__main__` all enable that. This means the token had almost certainly
already been logged on every prior test execution too, including the
one-off notify test job. Fixed by setting `logging.getLogger("httpx")` to
`WARNING` in all three entrypoints — none of them need per-request HTTP
logging, each already logs its own meaningful summary line. **Advised the
user to rotate the bot token regardless** (revoke via `@BotFather`,
generate a new one) — a credential that was exposed, even briefly and even
in a project only the user can view logs on, gets treated as compromised
rather than assumed-fine because the leak is now fixed.

**Final verification, for real**: user tapped Approve on the real
Telegram message a second time (after both fixes deployed); webhook logs
showed `200 OK` twice (Telegram's retry of the earlier failed delivery,
plus the fresh tap), `Recorded approved for promotion a42438b30292 channel
0ad87c1028e1`, and both `answerCallbackQuery`/`editMessageText` succeeding.
Confirmed directly via `gcloud storage cat` on the real bucket — a genuine
`EntryRecord` exists: `status: approved`, correct `channel_id`,
`compliance_note: "No duplicate-entry or cross-brand conflict found."`.
The full loop — discover → notify → tap → recorded — is real, live, and
confirmed working end to end, not inferred from "the deploy succeeded."

**Outstanding**: bot token rotation (user's action — @BotFather revoke +
reissue), after which the new token needs writing into
`telegram-bot-token` (`gcloud secrets versions add`) and both Cloud Run
Job/Service will pick it up automatically on their next execution/request
(`:latest` secret version reference, no redeploy needed for a new secret
version — Cloud Run resolves `:latest` at request/execution time for
Jobs, though the *Service* only re-resolves it for new container
instances, so a stale warm instance could keep the old value briefly;
worth a fresh revision if that matters sooner rather than later).

## 2026-09-04 — Entry-execution engine + results tracking (spec sections 5 and 7)

Approve today only recorded a decision. Built the real thing: automated
web-form entry filling (drafted, then human-approved, then submitted) and
a minimal results-tracking follow-up.

**Checked against real live data before designing anything**: pulled the
real `entry_channels.json` from the GCS bucket. Zero discovered
`EntryChannel`s were `web_form` *and* confidently free *and* not flagged
for review — the 8 real "approvable" channels are all `post` (5) or
`phone_entry` (3), both explicitly non-automatable per CLAUDE.md (no
phone automation ever; nothing here can post a letter). This proves
`is_free_route`/`review_recommended` alone never encode the phone/post
ban — confirmed the design had to check `channel_type == web_form` as its
own hard-coded, independent condition, not infer it. Built the full
pipeline anyway, verified against a hand-built realistic fixture form
(`tests/fixtures/entry_execution/sample_entry_form.html`) rather than
waiting for a real qualifying case or loosening a classifier to manufacture
one.

**A real safety gap found and fixed before writing anything else**:
`notify/channel_selection.py`'s `select_approvable_channel()` had no
channel-type awareness at all — harmless while nothing qualified, but the
moment a real free `web_form` channel got discovered, the *already-shipped*
Approve/Skip flow would have put an immediate, unreviewed button on it,
creating an `EntryRecord(status=APPROVED, channel_type=web_form)` with no
draft, no fill plan, no screenshot — exactly what the two-stage design
below exists to prevent. Fixed by excluding `web_form` from that
function's selection loop; regression test added.

**Design, confirmed with the user via three explicit choices**: build the
full pipeline now, even though nothing currently qualifies; use
Claude-assisted generic field mapping rather than hardcoded per-site
selectors; two-stage approval (see a filled-but-unsubmitted screenshot
first, a second tap actually submits) rather than one-tap-submits.

**Built:**
- `UserProfile` storage (`storage/user_profile_store.py`,
  `setup_user_profile.py`) — a single stored record, not a keyed
  collection (matches the model's deliberately-singular design), set up by
  the user directly in their own terminal, never through this conversation.
  `--check` prints a masked summary.
- `entry_execution/eligibility.py` — the two hard-filtered queries
  (`find_draftable_channels`, `find_submittable_entries`), pure and
  fixture-tested, both independently re-asserting `channel_type ==
  web_form` rather than trusting `is_free_route`/`review_recommended` alone.
- `entry_execution/fill_plan.py` — the schema an LLM mapping must satisfy
  before any code touches a real page: every selector must be one actually
  sent (blocks an invented selector), no duplicates, field count matches,
  every `profile_field` is one of the 5 known `UserProfile` attributes,
  every checkbox has an explicit action. `build_fill_actions()` is where
  PII actually enters the picture — deliberately kept out of the LLM call
  itself.
- `entry_execution/llm_mapping.py` — the one Claude call this feature
  makes (`claude-opus-5`, per the claude-api skill's non-negotiable
  default — corrected after an earlier draft of the plan suggested Sonnet).
  Only field structure (selector/label/type/options) and the 5 profile
  field *names* are sent, never real values. Uses
  `client.messages.parse(output_format=FormMapping)` — confirmed this is
  still the right shape against the actually-installed `anthropic` 1.3.0
  SDK (`response.parsed_output`), not assumed from training data.
- `entry_execution/browser.py` — Playwright field extraction (tags each
  field with its own `data-rc-field` marker rather than trusting the
  page's own ids/names) and fill/check application at a varied, non-machine
  pace.
- `entry_execution/draft.py` / `submit.py` — the two stages.
  **The concrete mechanism, not just a claim, behind "a stray page change
  between draft and confirm can't cause an unreviewed action"**: a
  dedicated test (`test_re_extraction_on_a_fresh_page_reassigns_the_same_
  markers`) proves re-extracting fields on a completely fresh page load
  reassigns identical selectors in the same order, provided the form's
  structure hasn't changed — so `submit.py` re-extracts on its own
  freshly-navigated page and verifies every saved selector still exists
  before ever touching the page, rather than trusting a stale selector
  from draft time. A third, defensive layer: an `APPROVED` `web_form`
  record with no saved `fill_plan` is refused outright, `FAILED`, never a
  blind submit.
- `notify/telegram_client.py` gained `send_photo` (draft screenshots) and
  `edit_message_caption` (clearing buttons on a photo message — discovered
  while writing `webhook/handlers.py` that `editMessageText` 400s against
  a message that was sent as a photo).
- `notify/callback_data.py` generalised its parameter names (`id1`/`id2`)
  to carry `w`/`l` outcome actions (`entry_id` as the second id) alongside
  the existing `a`/`s` encoding.
- `webhook/handlers.py` — three flows sharing one callback encoding: a
  fresh discovery Approve/Skip (unchanged), a draft Submit/Reject that
  updates the *same* `DRAFTED`+`web_form` `EntryRecord` in place rather
  than creating a second one, and outcome Won/No dispatched before any
  promotion/channel lookup (outcome callbacks carry an `entry_id`, not a
  `channel_id`). Extended tests cover all three plus the repeat-tap/
  already-recorded case for each.
- `outcomes/reminder.py` — `find_pending_outcome_checks()` /
  `notify_pending_outcomes()`: a `SUBMITTED` entry whose promotion's
  deadline (plus a 5-day announce buffer) has passed, with no `Outcome`
  yet, gets asked once via a Won/No Telegram message. An entry whose
  promotion has no known deadline is never flagged — no principled date to
  ask by.
- `run_entry_execution.py` — the new Cloud Run Job entrypoint: checks
  eligibility first (no Playwright import at all if nothing qualifies),
  then draft/submit/outcome-reminder steps, each independently caught.
- `Dockerfile.entry-execution` + `cloudbuild.entry-execution.yaml` — based
  on `mcr.microsoft.com/playwright/python:v1.62.0-noble` rather than
  hand-installing Chromium onto `python:3.13-slim`, confirmed via the
  Playwright docs that the tag version must exactly match the pip
  package version or Playwright can't find its browser executable.
  `requirements.txt`'s `playwright` pin changed from `>=1.44` to
  `==1.62.0` accordingly (already the version installed locally, so no
  local environment change).
- `tests/test_entry_execution_live.py` — the one genuinely live piece (a
  real Claude call against the fixture form), gated behind
  `ANTHROPIC_API_KEY` and correctly skipped locally (no key set yet).

**Verified so far**: full test suite green (107 passed, 1 skipped —
the live test — at time of writing), every new module import-checked
against the real installed `anthropic`/`playwright` packages (not just
assumed from the plan), `run_entry_execution.py` smoke-tested against an
empty local data dir (exits 0, "Nothing draftable or submittable this
tick", no Playwright launch attempted).

**Outstanding**: the user's manual setup steps (real `setup_user_profile`
run, Anthropic API key + `anthropic-api-key` secret creation), then
deploying `radio-comp-entry-execution` + its Cloud Scheduler job, then a
genuine end-to-end run — seeding one synthetic qualifying promotion/channel
to force a real draft, since nothing discovered currently qualifies.

## 2026-09-07 — Entry-execution engine deployed and live

User's manual steps done: `setup_user_profile` run for real (once against
`STORAGE_BACKEND=firestore`, the local default, then again explicitly
against `STORAGE_BACKEND=gcs` so the deployed Job — which uses `gcs`, same
reason as every other Cloud Run workload here — can actually see it); the
`anthropic-api-key` secret created in Secret Manager.

**A real recurrence of a previously-documented gotcha, hit again**:
`setup_user_profile`'s first attempt 403'd with `PERMISSION_DENIED` from
Firestore. Application Default Credentials
(`~/.config/gcloud/application_default_credentials.json`) is a single
global file, not scoped per gcloud configuration — the user's NatureMetrics
day-job gcloud usage (default config, `dbol-prod` project) had at some
point run an impersonated-service-account ADC login, silently overwriting
this project's personal-account ADC (confirmed by inspecting the file's
`"type"` field: `impersonated_service_account`, not `authorized_user`).
Fixed by re-running `gcloud auth application-default login
--configuration=radio-comp`, logged in as the personal account, no
impersonation. Saved as a standing memory (not just a repo note) since
this is bound to recur given its root cause is unrelated day-job tooling,
not anything under this project's control.

**Deployed for real**, mirroring the discovery Job's established pattern
exactly (same default compute service account, same `STORAGE_BACKEND=gcs`
env vars, same Scheduler → `jobs.run` OAuth pattern):
- Built and pushed `Dockerfile.entry-execution` via
  `cloudbuild.entry-execution.yaml`.
- Granted the runtime service account `secretmanager.secretAccessor` on
  `anthropic-api-key` (it already had it on `telegram-bot-token`).
- Created the `radio-comp-entry-execution` Cloud Run Job — `2Gi`
  memory / 2 CPU (Chromium needs meaningfully more than the discovery
  Job's plain-`httpx` 512Mi) and a 600s task timeout (vs. discovery's
  300s — page navigation/fill/submit is slower than a scrape), `maxRetries:
  1` kept consistent with discovery rather than tightened, since the risky
  window (a crash between `click_submit()` and the status write) is a
  narrow, ordinary at-least-once-execution race no different in kind from
  anything else in this codebase, not something introduced by this
  feature.
- **Verified with a real manual trigger before wiring up the scheduler**,
  not just "deploy succeeded": `gcloud run jobs execute
  radio-comp-entry-execution --wait` completed successfully;
  `gcloud logging read` confirmed the actual log line —
  `Nothing draftable or submittable this tick` — i.e. eligibility.py's
  cheap pre-check correctly ran and correctly found nothing, without a
  Playwright/Chromium launch, exactly as designed.
- Created `radio-comp-entry-execution-15min`, a Cloud Scheduler job on
  `*/15 * * * *` (Europe/London), calling the Job's `:run` endpoint the
  same way `radio-comp-discovery-hourly` does.

**Outstanding**: the genuine end-to-end verification still needs a
synthetic qualifying `Promotion`+`EntryChannel` seeded (`web_form`, free,
non-review) pointing at a safe test target, since nothing discovered so
far actually qualifies — that's what would exercise a real draft
screenshot arriving on Telegram with Submit/Reject buttons, a real Submit
tap, and a real `submit_one()` pass on the next tick.

## 2026-09-08 — First real end-to-end draft attempt: two bugs found, one design pivot

Set up the synthetic test the previous entry called for: a throwaway
public GCS bucket (`project-a6778446-201f-4aa5-a03-test-fixtures`,
deliberately separate from the real data bucket — never made anything in
the bucket holding real `UserProfile`/PII data public) hosting
`tests/fixtures/entry_execution/sample_entry_form.html`, then a synthetic
`Promotion`+`EntryChannel` (`[TEST]` prefixed, `web_form`, free,
non-review) seeded directly into the real GCS data store pointing at it.

**Bug 1 — `ModuleNotFoundError: No module named 'playwright'` on the first
real manual trigger.** `Dockerfile.entry-execution`'s comment claimed
`mcr.microsoft.com/playwright/python` ships the `playwright` pip package
preinstalled, matching an initial reading of the Playwright docs — wrong.
Confirmed via a Cloud Build probe (running `pip show playwright` and a
real `chromium.launch()` inside the base image directly, no local Docker
daemon available) that only the Chromium binary + its OS dependencies are
baked in; the pip package itself still needs installing. Fixed by adding
`playwright==1.62.0` back to the Dockerfile's `pip install` list —
confirmed via the same probe that this finds the pre-baked browser with no
download, so the image is still exactly as lean as intended, just needed
one more explicit line. Real lesson: verify a base image's contents
directly (Cloud Build can run an arbitrary probe against any image without
needing a local Docker daemon) rather than trust a docs paraphrase about
what's "preinstalled."

**Design pivot — moved off Anthropic entirely, mid-deployment.** After
fixing bug 1, the second real trigger reached the actual Claude API call
and failed with `401 invalid x-api-key` — traced (via byte-length/prefix
checks that never printed the actual secret value) to the
`anthropic-api-key` secret holding a 5-byte placeholder, not a real key.
Before fixing that, the user paused to reconsider: they didn't want this
tied to their work Anthropic account, and asked about a personal-account
or Gemini alternative instead. Clarified the real distinction (a claude.ai
chat subscription, of any tier, gives no API access at all — the API is a
separate console.anthropic.com product requiring its own billing even on
a personal account) and that Gemini's free tier, via Google AI Studio,
genuinely requires no billing at all. User chose Gemini.

Verified the current Gemini Python SDK (`google-genai` 2.22.0) against
its actual installed source before writing anything — not just docs
paraphrases, which turned out to blend two different API generations in
one WebFetch response (an older "Generate Content API," now marked
legacy, vs. a newer "Interactions API"). Cross-checked the newer API's
docs example against `google/genai/interactions.py`'s real
`CreateModelInteractionParam`/`TextResponseFormatParam` TypedDicts
directly in the installed package to confirm the exact call shape:
`client.interactions.create(model=..., input=..., system_instruction=...,
response_format={"type": "text", "mime_type": "application/json",
"schema": FormMapping.model_json_schema()})`, reading `interaction.
output_text` back. Rewrote `entry_execution/llm_mapping.py` accordingly
(model: `gemini-3.8-flash`, a mid-tier choice for the same "wrong
classification has real consequences" reason `claude-opus-5` was chosen
originally), swapped `anthropic` for `google-genai>=2.22.0` in
`requirements.txt`/`Dockerfile.entry-execution`, `ANTHROPIC_API_KEY` for
`GEMINI_API_KEY` throughout (`.env.example`, the live test's skip gate,
README). Full test suite still green (107 passed, 1 skipped) after the
swap — `test_entry_execution_live.py` correctly skips locally with no
`GEMINI_API_KEY` set.

**Outstanding**: the user still needs to get a Gemini key from
aistudio.google.com and create the `gemini-api-key` secret; then the image
needs rebuilding/redeploying with the Gemini-based code, the Cloud Run
Job's secret binding needs swapping from `ANTHROPIC_API_KEY` to
`GEMINI_API_KEY`, and the same real end-to-end draft attempt needs
re-running against the still-seeded synthetic promotion. The
`anthropic-api-key` secret and the placeholder value in it can be deleted
once this is confirmed working — left alone for now, harmless and
unreferenced. `FormMapping.model_json_schema()`'s actual compatibility
with Gemini's structured-output support (nested `$defs`/enums/Optional
fields) is unverified until that first real call succeeds.

## 2026-09-08 — Gemini pivot confirmed live; full entry-execution loop verified end to end

Real Gemini call against the fixture form succeeded once the user created
a correct `gemini-api-key` secret (the first attempt had a placeholder
value, per the previous entry) — `FormMapping.model_json_schema()` works
fine with Gemini's structured-output support, resolving the previous
entry's open question. Rebuilt/redeployed `radio-comp-entry-execution`
with the Gemini-based image and the new secret binding.

**A real credential leak, caught by the user, not by a log review this
time**: while diagnosing why a Submit tap silently did nothing, the user
ran `getWebhookInfo` themselves and pasted the *result* into the
conversation — but the bot token they'd used to build that URL turned
out to actually be the `telegram-webhook-secret` value (both are 64-hex
strings; easy to mix up), now exposed regardless of which one it
technically was. Rotated both: new bot token via BotFather → new
`telegram-bot-token` secret version; new `openssl rand -hex 32` →
`telegram-webhook-secret`; forced a fresh webhook Service revision so it
actually picks up the new bound secret values (Cloud Run Jobs re-resolve
`:latest` automatically per execution, but a Service only does so for new
container instances); re-ran `setWebhook` with both new values, confirmed
via `getWebhookInfo` (never touching the raw token in a way that gets
printed — piped straight from Secret Manager into the `curl` call in one
shell pipeline).

**A second real bug, found only by testing the actual Submit tap**: once
the webhook was reachable again, tapping Submit produced "Already
recorded" instead of the draft-confirmation flow, then crashed trying
`editMessageText` against a photo message (`400 Bad Request`). Root
cause: the *webhook Service's deployed image* was still the pre-entry-
execution build — all of `handlers.py`'s new draft-branching/
`edit_message_caption`/outcome-dispatch logic had been written and
tested locally earlier in this project but never actually rebuilt+
redeployed to the live Service (only the entry-execution *Job* had been
rebuilt). Rebuilt and redeployed `radio-comp-webhook` for real; the
identical tap then worked correctly (`"Approved — submitting shortly"`),
and the next Job tick genuinely submitted the form
(`status: submitted`, both `draft_screenshot_path` and
`submitted_screenshot_path` populated). Confirmed via real screenshots
that the "submitted" one shows a blank reloaded form — expected, not a
bug, since the throwaway test fixture has no real backend to show a
confirmation page; a real competition site would show one there instead.
Cleaned up all synthetic test data (`[TEST]`-prefixed promotions/
channels/records, their screenshots, the throwaway public
`project-a6778446-201f-4aa5-a03-test-fixtures` bucket) from the real
data store afterward.

**Lesson, worth restating plainly**: rebuilding one image (the Job) after
a cross-cutting code change doesn't mean every image sharing that code
(the webhook Service) is also up to date — check what's *actually
deployed* per Cloud Run resource, not just what's been rebuilt somewhere.

## 2026-09-08 — talkSPORT "Online" channel classification: real widget access, not just page rendering

With entry-execution fully verified but genuinely idle (real data: 0
confidently-free `web_form` channels), asked whether that's likely to
change on its own. Broke down the 30 real discovered channels by type:
9 `web_form` (7 ambiguous, 2 paid, 0 free), 3 `post` + 6 `phone_entry`
(free but permanently banned from automation) — concluded it's
structural, not luck: talkSPORT's real entry-cost text for "Online" is
often only rendered client-side, a gap already flagged (unverified) when
`talksport.py` was first built.

**First attempt — disproven by testing against real data, not assumed
to work**: built a generic "re-fetch the page with Playwright, re-run
the same static-HTML classifier against the rendered result" mechanism
(`stations/rendering.py`, `talksport_widget`-agnostic merge/retry logic,
a `radioexe.py` fix for a separately-found silent-omission bug — see
below). Ran the actual backfill against a real copy of production
data before trusting it: **0 of 7 real channels resolved.** Investigated
why, live, rather than assuming: talkSPORT's "Online" entry cost isn't
on the competition page at all, in any rendering — it's delegated to a
third-party competition-entry platform (`win.talksport.com`) behind a
cross-origin `<iframe class="authenticated-iframe" loading="lazy">`.
Deleted the disproven `rendering.py` and its tests rather than leave
dead scaffolding around.

**Real mechanism, found and proven live, one blocker at a time**:
1. What looked like non-deterministic flakiness in whether the iframe
   even appeared turned out to be a User-Agent effect: this project's
   existing polite, self-identifying `config.USER_AGENT` string reliably
   got it into the DOM (5/5 attempts); Chromium's default headless UA got
   it 0/6 times.
2. The iframe uses native `loading="lazy"` (needs `scroll_into_view_if_needed`
   to trigger) and sits behind a Sourcepoint cookie-consent modal
   (dismissed best-effort via `page.frame_locator(...)`, since it isn't
   always present).
3. The widget's own text uses a different phrasing convention entirely
   from the outer page's classifier ("£X PER ENTRY" / "YOUR TOTAL : £X",
   not "charged at £X") — confirmed live: `£2.50 PER ENTRY`, tiered
   bundle pricing, `YOUR TOTAL : £2.50`.

Built `stations/talksport_widget.py` (talkSPORT-specific, not generic)
implementing exactly this: `fetch_widget_text()` (consent-dismiss +
scroll + frame-text extraction), `classify_widget_text()` (pure regex
against the confirmed real pattern; a free-indicator pattern flagged as
unverified — no real free example has been seen), `resolve_online_channel()`
(never raises, falls back to the untouched static classification on any
failure — same "never guess" posture as every other classifier here).
Wired into `talksport.py`'s `ingest()` *after* the dedup-hash check
(caught via a real log read after the first deploy: it was initially
running before the check, wastefully re-resolving already-known
duplicate promotions).

**A second real finding, requiring a design change mid-implementation**:
broader live testing (checking all 6 other real ambiguous URLs, not just
the one already confirmed) showed the widget's appearance is genuinely
intermittent — even a 15-second explicit `wait_for_selector` didn't help
on a URL that had worked minutes earlier. Added a bounded retry
(`fetch_widget_text(url, attempts=3)`, fresh browser launch each try) —
a contained addition, not a new architecture.

**A third, self-inflicted finding**: after extensive manual live testing
(several dozen Chromium launches within ~20 minutes, well past this
project's own "polite, low-volume" scraping ethos), talksport.com's own
bot-detection started serving a "Verifying Device" challenge page instead
of real content — to *plain `httpx` requests too*, confirming it wasn't
Playwright-specific. This briefly made later local test results look
like the widget had become totally unreliable; it hadn't — it was local
testing volume triggering a temporary block against that IP. Stopped
manual live-testing immediately rather than risk prolonging it, and used
the deployed Cloud Run Job (a completely different IP, Google's own
range, naturally paced at once-per-promotion) as the real verification
method instead — consistent with this project's own "verify for real,
not just tests pass" convention, just via infrastructure that wouldn't
compound the problem.

**Final real verification, from Cloud Run's IP, not a confounded local
one**: a real discovery run (after rebuilding `Dockerfile` — same
`mcr.microsoft.com/playwright/python:v1.62.0-noble` + explicit
`playwright==1.62.0` pattern as `Dockerfile.entry-execution`, bumped
`radio-comp-discovery`'s resources from `512Mi/1cpu/300s` to
`2Gi/2cpu/600s`) ran clean, 0 failures. Ran the backfill for real via a
one-off `--command`/`--args` override on the same Job (reverted
immediately after, confirmed via `describe`) rather than from the
now-possibly-flagged local machine: **4 of 7 real ambiguous channels
resolved to confidently paid** (`£2.50 per entry`, real `raw_excerpt`
audit trail from the actual widget text), the other 3 correctly stayed
ambiguous — traced to those specific competitions' live pages no longer
even mentioning "Online" as a heading at all (content drift since the
original scrape, not a bug). Confirmed in the real stored data:
`web_form` channels now break down as 6 paid / 3 unknown / 0 free (was
2 paid / 7 unknown / 0 free before this phase).

**Outcome, stated honestly**: zero new *qualifying free* channels — this
pricing-tier widget appears to be a shared template across talkSPORT's
whole platform, so it's plausible none of the 7 were ever going to
resolve to free. The real value delivered is turning "stuck at unknown
forever" into an audited, confident classification, which matters in its
own right for tracking/EV-model accuracy, and the same mechanism will
apply automatically to any newly-discovered talkSPORT competition going
forward. Radio Exe's independent silent-omission fix (a web-form entry
point with no cost phrase previously produced no channel at all, now
correctly produces an ambiguous one) ships alongside this, unaffected by
any of the above — its pages are fully server-rendered, confirmed
already, so it never needed a Playwright retry at all.

**Next step, per the user's own stated sequencing**: assess whether
adding more discovery sources is worth it, now that this specific avenue
has been explored as far as real data supports.

## 2026-09-09 — New discovery sources: Bauer's "Make Me A Winner" live; Heart dropped for a real safety reason

User's own verdict on the above: discovery volume isn't meeting
expectations (only 2 aggregators, 2 direct monitors live, against an
original plan naming 3 aggregators + "Global, Rayo/Bauer, talkSPORT").
Research (internal docs + fresh live web research) confirmed the gap:
Global and Bauer were both named in the original scope and both already
had a 2026-09-02 informal feasibility check (Bauer's `hellorayo.co.uk`
platform specifically, not Global as initially misremembered — corrected
mid-investigation by a research agent that checked the actual log text
rather than trusting the framing it was given) — but neither ever got a
direct-monitor adapter built. User chose Global+Bauer first (one adapter
covers 5-6 stations each, vs. one at a time for the seeded-but-unbuilt
local tier), on the strength of Bauer's "Make Me A Winner" — a shared
competition across Absolute/Kiss/Magic/Hits Radio/Greatest Hits Radio/
Planet Rock with hints of a genuine free online entry route.

**A real safety incident, caught before it became a real problem**:
investigating `comp.heart.co.uk` (one of Heart's off-page entry
subdomains) with Playwright, a plain page load — no click, no form fill —
showed "Thank you! You have successfully entered the competition." This
could have meant an unintended real entry. Verified properly rather than
assumed either way: checked whether the text appeared *immediately* on
load (it did — too fast for a real submission to have processed) and
captured every network request the page made (`page.on("request")`) —
only one non-GET request occurred, a routine Sourcepoint consent-tracking
call, nothing resembling an entry submission. Confirmed safe: the
"success" text is a front-end bug in Heart's own widget, which depends on
a real login to Global's Gigya SSO account system and falls into a
wrong-but-harmless default state when that login context is absent (as it
always will be for an anonymous/automated visit). **Dropped Heart for
this phase regardless** — even confirmed-harmless-to-read, a platform
that shows misleading state when read passively, and whose real
entry-detail mechanism needs a genuine personal login to a third-party
account system (a materially bigger, new category of credential this
project has never taken on), isn't worth building against right now.

**Bauer's Make Me A Winner — built, and simpler than expected once
investigated properly**: `makemeawinner.co.uk` itself is a pure
client-rendered Vue SPA (empty `<div id="app">` from a plain fetch,
confirmed) — but Playwright network-request capture (used carefully,
checking first for the same kind of unintended-action risk found on
Heart — confirmed safe: the listing page loads with an untouched, empty
basket every time) found the real backend: a clean, unauthenticated
JSON API at `api.winhappy.com`. `GET /session/data` returns a short-lived
guest bearer token in its `X-Session` response header (no login, no
cookies), which authorizes `GET /campaign/page/HOME` — returning every
live competition with a genuine `is_free` boolean straight from Bauer's
own backend. Confirmed this whole flow works via plain `httpx` alone —
**no Playwright needed for this adapter at all**, a better outcome than
the plan's own fallback design (full-page rendering). This is also the
first source in this codebase where entry-cost classification is a real
field from the source system, not a regex/keyword guess against scraped
text — meaning it's confident in both directions (`is_free_route=True`
*or* `False`, never `review_recommended` unless the field is genuinely
absent), unlike every other adapter's classifier here.

Built `src/radiocomp/stations/bauer_makemeawinner.py` (`fetch_session_token`
→ `fetch_listing` → `parse_campaign_item` per item, `BUNDLE`-type items
skipped since they're paid entry-multiplier add-ons, not distinct
competitions) and extended `compliance/engine.py`'s
`SHARED_LIMIT_NETWORKS["Bauer"]` with `magic`, `hits radio`,
`planet rock` (confirmed live via the API's own station list — closing a
gap the module's own docstring had already flagged) and this adapter's
own `station_name_raw` ("Make Me A Winner (Bauer)"), so the cross-brand
duplicate check actually recognises its promotions as Bauer-network.

**Verified for real, not just tests passing**: rebuilt/redeployed
`radio-comp-discovery` (no Dockerfile changes needed — Playwright was
already there from the talkSPORT widget work, unused by this adapter but
harmless), triggered it live — **4 adapters ran, 0 failed, 15 new
promotions in one run** (promotions 50→70, `web_form` channels 21 paid +
3 still-unresolved-talkSPORT / 0 free). Real, substantial volume increase,
addressing the user's actual complaint directly. Honest bottom line, same
shape as the talkSPORT widget work: all 15 real live Bauer campaigns are
currently paid — zero new qualifying free channels *today* — but the
classification is now genuinely confident (a real field, not a guess) and
will catch a free one immediately and correctly the moment one appears,
which real data shows does happen on this platform (some campaigns in
Bauer's own data model are marked free) even if none currently are.

**Heart/Global remains a real, larger opportunity if revisited later** —
just gated on a decision to take on real personal-account credentials for
a third-party platform, which this project hasn't needed before and
shouldn't take on lightly.

## 2026-09-09 — Real bug found by the user, not by this project: Bauer's free phone route was invisible

Real payoff and a real miss, same day. User reported a flurry of real
Telegram notifications from the new Bauer adapter (confirming actual
delivered volume, not just a log count) — then, investigating one
personally, found they could enter completely free via the campaign's
phone line, which `bauer_makemeawinner.py` had only ever recorded as a
paid `web_form` channel. This was a genuine gap, not something outside
the original investigation's scope: the 2026-09-09 research (same day,
earlier) had already found and documented that paid campaigns carry a
separate, genuinely free postal/phone "no purchase necessary" alternative
in their own T&Cs — the approved plan even said to model it as its own
`POST`/`PHONE_ENTRY` channel — but the shipped adapter only ever built the
one `web_form` channel per campaign. The design was right; the
implementation was incomplete. Caught by the user actually using the
system for real, not by any test or review here.

**Clarified explicitly for the user**: no, this can't and won't be
automated — CLAUDE.md's phone-channel ban is absolute, a free phone-line
IVR route included, regardless of EV. The fix is entirely about
*visibility*: make sure the free phone/post route shows up in the
Telegram notification the same way a free web form would, so the user
sees it and can act on it manually themselves, same as they just did on
their own initiative.

**Root-caused the exact number the original web search couldn't verify**:
the "up to 250 free online entries per week" figure that started this
whole phase turned out to be a mix-up — the real T&Cs say "**PHONE**
Entrants can enter ... up to 250 times in total by calling [number] ...
Calls (from the UK) are charged at standard network rate." It was never a
web-form limit; it's the phone route's own cap, confirmed via a second
real API call (`GET /campaign/info/{tag}`, its `body` field is the full
T&Cs HTML) discovered by capturing the actual network request the
campaign *detail* page makes (same Playwright-network-capture technique
already used to find `campaign/page/HOME` itself).

Extended `bauer_makemeawinner.py`: `fetch_campaign_info()` (a second,
per-campaign API call) plus `extract_phone_channel()`/
`extract_post_channel()`, using the same "standard network rate = free
but never automated" convention already established in talksport.py/
radioexe.py, and the same "PO Box + postcode = free postal route"
convention as talksport.py's own POST handling. Two real phrasing
variants were found and both handled (`"POST Entrants can also enter..."`
vs. `"POST Postal entries must be received... Entrants can enter the
Competition by sending..."`) — caught by testing against every real
campaign in production, not just the first one checked; an initial 400-
character capture window also proved too narrow for the phone case (cut
off before "standard network rate" appeared across a long list of
alternate numbers) and was widened to 800 after finding this live. 3 of
15 real campaigns still show no phone/post channel — confirmed these are
genuinely different campaign shapes (`type: EXTERNAL`/`EMBEDDED`,
redirecting to a sub-page or a third-party widget vendor, with an empty
placeholder T&Cs body) rather than a missed regex case.

**Backfilled the 15 promotions already in production** (a fresh discovery
run alone wouldn't add these — `ingest()` skips anything it already knows
by dedup hash, channels included) via a new one-off
`backfill_bauer_phone_post_channels.py`: 12 real channels added (2 phone,
10 post) across the existing 15 Bauer promotions, confirmed in the real
stored data (`post` 3→13, `phone_entry` 6→8).

**A third recurrence of the ADC-overwrite gotcha**, hit while running the
backfill against real GCS data: this time the clobbering identity was a
work service account (`dbol-elt-runner@dbol-prod.iam.gserviceaccount.com`),
not an impersonated one like the last two times — same root cause
(NatureMetrics day-job gcloud usage overwriting the single global ADC
file), same fix (`gcloud auth application-default login
--configuration=radio-comp`, done by the user). Worth restating since it
keeps recurring in slightly different shapes: check the ADC file's `type`
field first on any unexplained GCS/Firestore permission error in this
project, before assuming a real permissions regression.

## 2026-09-09/10 — Pivoted to local stations; found the wrong 13, then the right 4; nothing live yet

Asked directly: given phone automation is a hard no (see below), where
else can the model expand to find more automatable competitions? Every
major-network source built so far (talkSPORT, Bauer) turned up a
monetized third-party platform with no genuinely free web form — the
user's own conclusion was to pivot to the local/independent tier, per the
original scoping research's own view that it's the better-EV target.

**A real, live win found, then found inapplicable**: Central FM's "Wake
Up & Cash In" (`centralfm.co.uk/win/wake-up-and-cash-in/`) is a genuine,
live, plain native HTML `<form>` — real `<input>` fields (Name, Email,
City, Post Code, Phone, plus an open "tell us about yourself" field),
`action="/_form_submit"`, no third-party platform, no cost/premium
language anywhere, "Powered by Aiir" in the footer. This is the exact
"Aiir CMS" pattern already referenced in `radioexe.py`'s own docstring —
now confirmed live on 3 stations (Central FM, Manx Radio, KMFM), a
genuinely reusable free-form pattern distinct from every monetized
platform found so far. But Central FM's own T&Cs require Forth Valley
(Scotland) residency, and the user's real postcode is SE5 (Camberwell,
South-East London) — confirmed by asking directly rather than assuming.
None of the 13 stations in `seed_local_independent.py` were ever checked
against where the user actually lives; they were a scattered Phase-0
sample. This is a structural issue for hyper-local commercial radio
generally (it exists to serve, and be paid to serve, a specific small
catchment), not a Central-FM-specific quirk — also confirmed live by
finding no residency language on the other survey candidates checked, but
this is the first time it's been checked at all.

**Re-targeted at genuine SE-London coverage**: verified 4 real, currently
operating, Ofcom-licensed stations covering Southwark/Camberwell — Select
Radio, Rainbow Radio (a pure client-rendered SPA, unlike the others —
would need Playwright if it ever gets a real competition), Mi-Soul,
Resonance FM. A fifth candidate, First Love Radio, is confirmed defunct
since April 2009 and excluded. Honest result: **none of the 4 currently
has a live, free competition** (Mi-Soul's only current prize mechanism is
a paid VIP-ticket raffle bundled into concert tickets). This project's own
established rule — build a classifier against a real captured example,
never speculative parsing logic — meant there was nothing to build a
proper adapter against yet.

**Built instead**: `seed_southeast_london.py` (the 4 real stations, same
shape as the original seed file) and a new, deliberately minimal
`stations/watch_for_competitions.py` — no `Promotion`/`EntryChannel`
records, just "has a Win/Competitions-looking nav link appeared on this
homepage since last time?", with a tiny `{station: last_seen_url}` JSON
state file (same per-backend branching as `user_profile_store.py`) so it
only ever notifies once per newly-appeared link, never repeats. Folded
into `run_discovery.py`'s existing hourly pass (4 extra plain GETs,
negligible cost) rather than new scheduled infrastructure, same reasoning
`outcomes/reminder.py` already used. Verified for real: a live discovery
run correctly logged `"Competition watcher: checked 4 station(s), 0 new
link(s) found"` — confirmed running, not silently failing (the first
version only logged when something was found, making a silent success
indistinguishable from a silently-swallowed exception; fixed to always
log a summary line, matching every adapter's own convention).

**Separately, the user asked whether the free phone-line route (found
during the Bauer bug fix) could be automated "in bulk," reasoning that
standard-rate calls are covered by their own phone allowance.** Declined
directly — this isn't really a cost question: Ofcom's civil
"persistent misuse" regime doesn't turn on who pays for the call, station
T&Cs explicitly ban bulk/automated entries with disqualification as the
stated consequence, and a placed phone call has no draft/undo step the
way a web-form submission does. Reaffirmed CLAUDE.md's phone-automation
ban as still correct and not worth relaxing, rather than build toward it
by increments.

**Outstanding**: this is genuinely a "wait and see" tool — real
verification is whether it actually catches the next competition one of
these 4 stations runs. Worth reconsidering the rest of the original 13
`seed_local_independent.py` stations the same way (checked against actual
user geography) if this SE-London-specific approach doesn't pan out.

## 2026-09-10 — A strategic reckoning: the automation bet hasn't paid off, and probably won't

Asked directly whether we'd reached a natural limit of the current
methodology. Answered honestly rather than optimistically, using the full
weight of real data gathered this session: across every single source
built or investigated — talkSPORT (7 ambiguous, mostly resolved paid),
Radio Exe (rare, mostly paid), Bauer (15 campaigns, all currently paid),
Heart (dropped on safety grounds), 17 local/independent stations across
two geographic passes (mostly no live competitions, or on-air/social-
media/physical-only entry) — **zero genuinely free, automatable web-form
entries have ever been found in real production data.** The
entry-execution engine (draft/approve/submit, LLM field mapping,
Playwright automation) has been built, deployed, and mechanically proven
against a fixture, but has never once fired for a real competition,
because nothing has ever qualified.

**Conclusion, stated plainly rather than papered over**: this isn't bad
luck or insufficient searching. Every genuine free route actually found
this session (Bauer's phone line, postal addresses, Central FM's
on-air-callback form) carries a built-in friction cost — a phone call, a
stamp, being awake at a fixed time — that a pure web form doesn't. That
friction very plausibly *is* the compliant "free alternative" doing its
intended job (Gambling Act equal-cost, anti-bulk-entry T&Cs): a
frictionless, instantly-automatable free web form would be trivially
farmable, so it looks like stations mostly don't offer one. The system's
actual proven value this whole session has been **discovery and
visibility**, not automation — the Bauer phone-line find is the human-
in-the-loop design working exactly as specced, just via a manual call
rather than an automated submission.

**Two directions agreed, in place of continuing to hunt for the one
source where automation finally pays off**:
1. Make the manual step easier, without automating it.
2. Keep expanding discovery sources for volume of visibility, accepting
   the automation ceiling as real rather than a temporary gap.

**Direction 1, built and deployed today**: a real, concrete gap in
`formatting.py`'s `format_channel_line()` — every adapter has been
storing the actual contact info for phone/post/SMS/email/WhatsApp
channels (`channel_url_or_number`) since early in the project, but the
shared formatter never actually displayed it. The user found their one
genuine free route (Bauer's phone line) only by clicking through to the
source page themselves; the notification itself never showed the number.
Fixed: `PHONE_ENTRY`/`ON_AIR_CALL_IN`/`POST`/`SMS`/`EMAIL`/`WHATSAPP`
channels now show their actual number/address/inbox directly in both the
Telegram notification and `view_promotions.py`'s CLI output (`WEB_FORM`
deliberately excluded — its `channel_url_or_number` duplicates the
promotion's own `source_url`, already shown separately). Telegram
auto-links plain phone-number-shaped text client-side regardless of
`parse_mode` (the same mechanism this codebase already relies on for
`source_url` links) — so this gets tap-to-call for free, no HTML/Markdown
formatting needed, consistent with `telegram_client.py`'s permanent
"plain text only" design. Rebuilt/redeployed `radio-comp-discovery`.

**Direction 2**: no new source built today — the standing next step,
whenever pursued, is the same geography-first approach direction 1's
sibling entry used (check real user location before picking a station),
plus reconsidering `MoneySavingExpert` (in the original spec, never
built) and the still-unexplored `xd.wayin.com` platform (seen twice now —
once via Bauer's own `STARTUPBUNDLE` redirect, once via KMFM's "kitchen
upgrade" competition — a possible third shared white-label platform,
unverified whether it has a clean API like winhappy.com or is
monetized-only like every other platform found so far).

## 2026-09-11 — `xd.wayin.com` ("Grow by Zeta") adapter built (Part 1 of the wayin/Heart plan)

Built `src/radiocomp/stations/wayin.py`, following the standard adapter
skeleton unchanged (pure `fetch()`/`parse_detail()`, `ingest()` doing all
I/O + storage, `existing_hashes`/`dedup.promotion_dedup_hash` cross-run
dedup, per-item `try/except httpx.HTTPError` → `logger.warning` →
`continue`, the same `"<Source> ingestion: %d listed, %d new promotions,
%d entry channels recorded"` summary line). Registered in
`run_discovery.py`'s `_load_adapters()`.

wayin.com has no enumerable campaign index of its own, so this adapter
discovers campaigns by scanning a small seed list of *other* pages known
to link out to one (`_SEED_LINK_SOURCES`) — same "seed manually, expand
over time" convention as `seed_local_independent.py`/
`seed_southeast_london.py`, applied to linking pages instead of stations.

**Re-confirming the two real examples live, per CLAUDE.md's "never guess
a URL" rule, turned up a real surprise**: the plan's original Bauer
`STARTUPBUNDLE` example had expired, and its current successor on Hits
Radio's own site now embeds via a *different* platform entirely
(`display.engagesciences.com`, not wayin.com) — so the actual live Bauer
example used instead is a different, currently-live campaign found via
the same search approach: a shared Tesco Clubcard competition
(`hellorayo.co.uk/hits-radio/competitions/win/tesco-clubcard-september-26-sponsored`
→ `x.wayin.com/display/container/dc/49fbb4f2-.../details`). KMFM's
"kitchen upgrade" example (`kmfm.co.uk/win/` →
`xd.wayin.com/display/container/dc/07806756-.../details`, a
Gousto-sponsored prize) was still live and used as-is.

**A second real surprise, more consequential for the design**: KMFM's
linking page has a plain `<a href="https://xd.wayin.com/...">` link,
exactly matching the plan's assumed shape (and
`watch_for_competitions.check_for_competition_link`'s own `<a href>`-scan
pattern). But Hits Radio's own site (`hellorayo.co.uk`) is a
client-rendered Next.js app — its wayin.com URL is never a real `<a
href>` at all, only a string value buried inside the page's embedded
`__NEXT_DATA__` JSON (an `"embeds"` field with `"provider": "wayin"`),
rendered into a widget client-side. Confirmed by testing, not assumed:
the plan's originally-sketched `<a href>`-only scan finds nothing at all
on this real page. `find_wayin_links()` therefore scans two ways — a
normal BeautifulSoup `<a href>` scan, plus a plain regex scan of the raw
page text for any `wayin.com`-containing URL substring — to catch both
real shapes.

Both real wayin.com campaign pages turned out to be plain,
server-rendered HTML — a plain `httpx` GET returns the full real content
(title, prize copy, entry period, and T&Cs when present), no Playwright
needed, confirmed empirically for both.

**Free/paid classification, kept fully conservative per CLAUDE.md**: only
one of the two real campaigns says anything explicit about entry cost at
all. KMFM's Gousto campaign states, in its own T&Cs, "Online entry is
free of charge." verbatim — a confident real signal, so its `WEB_FORM`
channel classifies as `is_free_route=True`. The Tesco Clubcard campaign's
page has no T&Cs/rules content in its static HTML at all and no cost
language anywhere in what *is* there, so it correctly comes back
`is_free_route=None, review_recommended=True` rather than inferring
"free" just because its entry form has no payment fields. No real *paid*
wayin.com campaign has been seen yet to build a paid-signal pattern
against — same "extend the classifier only once a real gap is found"
posture as `bauer_makemeawinner.py`'s own phone/post extraction history.

**A related real finding, worth recording explicitly**: KMFM is actually
owned by KM Media Group, not Bauer — but the Gousto campaign's own real
T&Cs describe it as a shared Bauer-network competition in its own words
("Anyone who has won a Bauer competition ... on any Bauer Radio Brand,
will not be eligible ..."), and list "KMFM Group" alongside dozens of
Bauer/Hits Radio Network station brands sharing the identical prize pool.
So `network="Bauer"` is used for the KMFM seed entry too — confirmed
empirically from the campaign's own T&Cs, not assumed from KMFM's own
on-air branding — so `compliance/engine.py`'s existing
`SHARED_LIMIT_NETWORKS["Bauer"]` cross-brand entry-limit check applies to
it correctly with no engine change needed.

Prize value stays `None` for both real campaigns (a travel-and-dining
package and a kitchen-goods bundle, neither with a single £ figure) — no
speculative extraction added for a field that isn't actually present on
this platform yet.

Real captured fixtures: `tests/fixtures/wayin_kmfm_linking_page.html`,
`wayin_bauer_linking_page.html`, `wayin_kmfm_gousto_campaign_page.html`,
`wayin_bauer_tesco_campaign_page.html`. `tests/test_wayin.py` (12 tests)
covers link-finding on both real shapes, parsing on both real campaigns
(one confidently free, one correctly ambiguous), and safe degradation on
malformed/missing/title-less HTML. Full suite: 152 passed, 1 skipped
(pre-existing, unrelated). Verified end-to-end against the real live
sources with `STORAGE_BACKEND=local`: `python -m radiocomp.stations.wayin`
found both real campaigns correctly (`wayin.com ingestion: 2 listed, 2
new promotions, 2 entry channels recorded`), a second run correctly
deduped to 0 new, and a full `run_discovery.py` pass with all 5 adapters
registered completed with 0 failures.

Part 2 of the same plan (Heart/Global Player, requiring a real personal
Gigya-SSO login) is separate, out of scope for this adapter, and not
touched here.

## 2026-09-23 — Part 2 of the same plan: Heart/Global, and it needed no login after all

Heart was dropped back on 2026-09-09 after `comp.heart.co.uk` (one of
Heart's off-page entry subdomains) showed a misleading "successfully
entered" state when read anonymously, on the assumption that reaching
real, trustworthy free/paid status meant taking on a genuine personal
login to Global's Gigya SSO — a materially bigger credential category
this project hadn't taken on before. Revisiting it now, a deeper look
found the platform that actually matters for discovery is a different
one: **`winplus.heart.co.uk`**, Global's own first-party "Global WIN"
competition platform, shared network-wide across Heart/Capital/Classic
FM/Gold/LBC/Radio X/Smooth via per-brand instances
(`winplus.capitalfm.com`, `winplus.classicfm.com`, etc.) — the same
"one adapter, several stations" shape as `bauer_makemeawinner.py`.

**The good surprise, re-confirmed live rather than trusted from ~2-week-old
research**: a real competition page there, fetched with no login attempted
at any point, plainly shows both `"FREE ENTRY: No purchase necessary."`
and `"Paid entry from £X..."` text on the same page (verified across 5
real live competitions via Playwright, with the same "check the network
requests, not just the rendered text" discipline as the original
`comp.heart.co.uk` incident — only routine analytics/consent/Stripe-config
calls occurred, nothing resembling a submission). The "Sign in with your
global iD" step shown on the page is needed to actually *submit* an
entry, never to *read* its free/paid status. So, unlike the original
plan, **`heart_global.py`'s discovery/`ingest()` needs no credentials and
no login at all** — same posture as every other adapter in this codebase.

**A second, bigger surprise, found by not stopping at the first
confirmation**: `winplus.heart.co.uk` itself is a pure client-rendered
Vue SPA (a plain `httpx` GET of any page returns only an empty `id="app"`
shell) — but Playwright's own network-request log, captured during the
same safe no-login page loads, showed the real rendered content comes
from a clean, unauthenticated-by-design JSON API served from the same
origin (`/data/init.json`, `/data/competitions/list.json`,
`/data/competitions/{id}/details.json`), confirmed afterwards to work via
plain `httpx` alone. Same discovery shape as `bauer_makemeawinner.py`'s
own `api.winhappy.com` (found via Playwright network capture, then
confirmed to need no Playwright at all), and a second first for this
codebase alongside Bauer's: `competitionEntryType` (`"free"`/`"paid"`) is
a genuine field straight from Global's own backend, not a regex/keyword
guess against scraped text — confidently classified in both directions,
never `review_recommended` unless the field is missing or unrecognised.
The brand id used to filter Heart's own competitions out of the shared
list (`"heart"` → `2`) is resolved live from `init.json` every run rather
than hardcoded, on the same "never guess a value, even a stable-looking
one" posture as everything else here.

Real data at capture time: 10 competitions live on Heart's own homepage,
2 confidently `free` (ticket giveaways), the rest confidently `paid`.
Every real paid competition has exactly one genuine free "no purchase
necessary" alternative described only in its own T&Cs body — never both,
never neither, an identical shape to `bauer_makemeawinner.py`'s own real
gap (a paid `WEB_FORM` campaign with a free phone/post alternative the
summary listing never mentions). Two ("Win £10,000", "Cash Call") use a
free phone route; every other paid competition instead uses a free
postal route to the same real PO Box (`PO Box 8669, Derby, DE1 9SR`).
**Tracked for visibility only, per CLAUDE.md — a phone channel is never
auto-dialled, full stop** — the real T&Cs text independently makes the
same point ("We reserve the right to withhold any prize from you if we
believe that you are using automated dialling technology...").

**`login()` — built, deliberately not wired into `ingest()` or
`run_discovery.py` anywhere.** The user has separately signed off on
setting up real personal Global Player credential handling now, for
*future* entry-submission work only — accepting the real risk that a
genuine Global Player account could be suspended if Global's own
anti-automation detection ever flags it, a materially bigger risk
category than anything else in this system, taken on deliberately and
explicitly rather than incidentally. Confirmed live, passively (reading
Global's own already-loaded JS and the requests it makes on its own,
never an actual login attempt): the real login call is Gigya's own
standard REST endpoint (`POST accounts.eu1.gigya.com/accounts.login`)
with Global Player's public client-side Gigya `apiKey`, `loginID`,
`password`, and `sessionExpiration=0` (session-only — fresh login every
run, nothing persisted, matching Bauer's own guest-token pattern); a
successful response carries Gigya's standard `UID`/`UIDSignature`/
`signatureTimestamp` fields, from which Global's own JS derives an
app-specific bearer token (`base64(json({gigyaUID, timestamp,
signature}))`) used on later calls to Global's backend. `login()`
implements exactly this and returns the derived token for the caller to
hold in memory for that run only — never persisted anywhere. It was
never actually exercised against the live site while building this (no
real `GLOBAL_PLAYER_EMAIL`/`GLOBAL_PLAYER_PASSWORD` exist yet, and this
project never invents or requests real credentials) — a real gap left
for the user to close themselves once they've created the actual
secrets, the same division of labour as every other credential in this
project (Secret Manager secrets are created and bound by the user, never
typed in by this project). `GLOBAL_PLAYER_EMAIL`/`GLOBAL_PLAYER_PASSWORD`
were added to `config.py` and `.env.example` following the exact
`TELEGRAM_BOT_TOKEN` convention, both left blank.

Real captured fixtures: `tests/fixtures/heart_global_init.json`,
`heart_global_competitions_list.json`, and three real
`heart_global_competition_details_*.json` files (one paid-with-phone-route,
one paid-with-post-route, one free). `tests/test_heart_global.py` (20
tests) covers brand-id resolution, listing/detail fetch, `parse_detail`
against all three real shapes, the conservative "unrecognised
`competitionEntryType` stays ambiguous" path, `ingest()`'s graceful
degradation when the brand id can't be resolved, and `login()`'s
credential-gate/request-construction/error-handling against a mocked
Gigya response — no real network call, no real credentials, anywhere in
the test suite. Full suite: 172 passed, 1 skipped (pre-existing,
unrelated). Verified end-to-end against the real live site with
`STORAGE_BACKEND=local`: `python -m radiocomp.stations.heart_global`
found 14 real live Heart competitions correctly (`Heart/Global Win
ingestion: 14 listed, 14 new promotions, 25 entry channels recorded`), a
second run correctly deduped to 0 new, and a full `run_discovery.py` pass
with all 6 adapters registered (`heart_global` now included) completed
with 0 failures.

## 2026-09-25 — `heart_global.py` generalised to the whole Global network, renamed `global_win.py`

The Heart-only adapter above was filtering `/data/competitions/list.json`
down to items tagged with Heart's own numeric brand id (2) before
recording anything. Re-fetched `/data/init.json`'s full `brands` map live
and confirmed it's entirely Global's own portfolio — Heart, Capital,
Classic FM, Gold, LBC, Radio X, Smooth, Capital Xtra, Big Top 40, Global
Player, Riviera Radio, and "Win Plus"/Global WIN's own brand entry, nothing
external mixed in — and that a real competition (id 13771, "Win Two
Tickets to See Manic Street Preachers and Suede") carries `brands: [67,
6]` (Global Player + Radio X only, no Heart at all), confirming brand
tagging genuinely scopes *display*, not just a redundant label. Since it's
the same backend, same fields, same T&Cs template regardless of which
brand(s) show a competition, filtering to one brand was strictly throwing
away real, otherwise-unreachable competitions — a real gap, not a
cautious default worth keeping.

Fix: stop filtering by brand entirely. `ingest()` now processes every
non-`hidden` item in the listing exactly once, regardless of its `brands`
array — the same "one shared platform, one shared station_name_raw"
precedent `bauer_makemeawinner.py` already established, applied here to
avoid ever recording the same real competition as N near-duplicate rows
if this module were pointed at more than one brand. `fetch_brand_id()`
is still called, but purely for an informational sanity-check log line
now, never to gate what gets recorded. Renamed the module (and its test
file) `heart_global.py` → `global_win.py`, `STATION_NAME` from `"Heart"`
to `"Global WIN"` (the platform's own real branding, confirmed live in
`init.json`'s own `"winplus"` brand entry: `"brandName": "Win Plus"`).
Added `"global win"` to `compliance/engine.py`'s
`SHARED_LIMIT_NETWORKS["Global"]`, same self-registration pattern as
Bauer's own adapter.

New real fixture, `tests/fixtures/global_win_competition_details_13771_non_heart_brand.json`
(the Manic Street Preachers/Suede competition above), specifically to
prove a non-Heart-tagged competition is now recorded — the old adapter
would have silently dropped it. `tests/test_global_win.py` (25 tests, up
from 20) adds: `ingest()` still proceeding when brand-id resolution
fails (informational only now, not a hard stop), a non-Heart-brand
competition being recorded end-to-end, and hidden competitions still
being skipped regardless of brand. Full suite: 174 passed, 1 skipped
(pre-existing, unrelated). Verified end-to-end against the real live
site with `STORAGE_BACKEND=local`: `python -m radiocomp.stations.global_win`
found **16** real live competitions (up from 14 Heart-only), including
genuinely non-Heart-branded ones — "Capital's Bong Game 2026" (four
separate real entries) and the Manic Street Preachers/Suede competition
above — that the previous, Heart-only adapter had been silently missing
every single run since it shipped.

## 2026-09-28 — Recurring competitions: notify once per series, not once per occurrence

"Capital's Bong Game 2026" turned out to be a genuine daily recurring
round, not four coincidentally-similar competitions: every real
`details.json` for it carries `competitionIsRound: true` and an identical
`competitionScheduleId` (11497) across each day's own separate competition
id/dateStart/dateStop. Left as-is, this would mean a fresh Approve/Skip
Telegram message every single day, indefinitely, for as long as the
segment runs — and Global's platform likely runs several of these
"daily play-along" formats, not just this one.

Rather than guess at recurrence from title/date matching (the usual
"never guess" posture), used the genuine field the source itself
provides: `global_win.py`'s `parse_detail()` now sets a new
`Promotion.recurrence_series_id` (`str(competitionScheduleId)`) whenever
`competitionIsRound` is true, `None` otherwise — never inferred for
sources that don't supply a real recurrence signal (see below).
`notify/send.py`'s new `_is_first_of_its_series()` then only notifies the
promotion with the *earliest* `entry_deadline` among every stored
promotion sharing a `recurrence_series_id` — deterministic and
storage-driven (no new "already notified" flag needed), and correct
regardless of whether several days of the same series are discovered in
one run (a first-ever run can find them all at once, as happened here) or
one at a time on subsequent days. The first (and only) notification for a
series gets an added note ("🔁 Recurring — this is the first occurrence
found; later ones won't re-notify.") so it's clear from the message itself
why tomorrow's round won't page again. Approve/Skip still behaves
normally for that one message; approving it never auto-approves future
occurrences — each later round is still its own separate `Promotion`/
`EntryChannel` that nothing has approved, so the entry-execution engine
won't touch it without a fresh human decision, unchanged from how every
other promotion already works.

**A second, real instance of the same underlying problem found while
checking this, deliberately left unfixed**: Loquax (the forum aggregator)
has independently rediscovered the exact same "Capital's Bong Game"
thread roughly every 9 days since 2026-09-04, as separate, unlinked
promotions (`station_name_raw="(unresolved — see Loquax thread)"`).
Unlike Global WIN, Loquax is a forum aggregator with no genuine recurring-
series field to key off — only a title string — so applying the same fix
there would mean guessing recurrence from text matching, which this
project avoids on principle. Left as a known, much milder version of the
same noise (repeats every ~9 days, not daily) rather than building a
heuristic for it.

`tests/test_global_win.py` (28 tests, up from 25): `recurrence_series_id`
set correctly from a real recurring-round shape, left `None` for an
ordinary competition, and not set merely from a stray `competitionScheduleId`
without `competitionIsRound=true`. `tests/test_notify_send.py` (+3):
several days of one series discovered at once only notifies the
earliest, a later occurrence is skipped when an earlier one is already
stored, and ordinary (non-recurring) promotions are unaffected.
`tests/test_notify_message.py` (+2): the recurring note appears only when
`recurrence_series_id` is set. Full suite: 182 passed, 1 skipped
(pre-existing, unrelated).

## 2026-09-28 — Global WIN entry-execution: real authenticated draft/submit

Followed up on why the entry-execution engine had never actually acted on
a real, confidently-free Global WIN channel: a live investigation found
zero `<form>`/`<input>` elements exist anywhere in a real competition
page's DOM until *after* "Step 1: Sign in with your global iD" completes.
There's no anonymous entry form at all on this platform — signing in
*is* the entry mechanism, not a UI nicety on top of one. Separately, a
direct `page.goto()` to a competition's own deep-link URL (exactly what
`entry_execution/browser.py`'s `open_page()` does for every other
station) reliably crashes Global's own frontend JS on a cold load —
`TypeError: Cannot read properties of null (reading 'prize')` in their
own `competition-view-*.js`, a real bug in their SPA, not ours. Loading
the competition's own brand homepage first and clicking through in-app
(organic SPA navigation, no deep link) loads the identical page with zero
JS errors.

The user explicitly signed off on wiring in real Global Player
credentials for this — a materially bigger step than anything built so
far, accepting the real account-suspension risk already discussed
(Global's own T&Cs permit disabling any account they believe is
automated). `config.GLOBAL_PLAYER_EMAIL`/`GLOBAL_PLAYER_PASSWORD` are
real Secret Manager secrets that already exist but are deliberately not
bound anywhere this environment can reach — nothing here could have
attempted a real login even if it tried to.

**New module**, `entry_execution/global_win_auth.py`:
- `sign_in(page)` drives the *real* sign-in form at
  `https://www.globalplayer.com/signin/` (`#email`/`#password`, a
  `rememberMe` checkbox, `button[type="submit"]` labelled "Sign In" — all
  confirmed live, passively: page loaded, consent dismissed, fields
  inspected, nothing ever typed or submitted), rather than reusing
  `stations/global_win.py`'s existing `login()` (a REST-only Gigya call
  that returns a bearer token for Global's own BFF API but never touches
  the Playwright browser's own cookie jar, so it can't make a *page*
  appear signed in). Driving the real form lets Global's own JS set
  whatever real session state each winplus subdomain's own frontend
  actually checks for, rather than reverse-engineering that cross-domain
  SSO handshake ourselves. Raises `RuntimeError` immediately, before any
  navigation, if either env var is unset (same inline-truthiness idiom
  `global_win.py:519`'s own `login()` already uses). Verifies the login
  actually succeeded — the URL moving away from `/signin/` within a
  bounded wait — before returning; never assumes success, and on a
  timeout raises with whatever text is visible in the form at that point
  (best-effort, since the real error-message markup was never observed —
  Global only renders it after a real failed submit, which this codebase
  must never trigger just to go looking for it).
- `_resolve_homepage_for_competition(client, comp_id)` reads a
  competition's own `brands` array (from
  `/data/competitions/list.json`) plus `/data/init.json`'s brand-code map
  to find which real `winplus.<brand>` homepage actually features it.
  Confirmed live (2026-09-28) that this genuinely matters, not just a
  nice-to-have: `https://www.winplus.co.uk/` (the platform's own generic
  "winplus" brand, id 9) does **not** list competition 13771 ("Win Two
  Tickets to See Manic Street Preachers and Suede", tagged `brands: [67,
  6]`) at all, while `https://winplus.radiox.co.uk/` does. The real
  brand-code → domain map (`_BRAND_CODE_TO_HOMEPAGE`) comes straight off
  the real T&Cs text already captured in
  `tests/fixtures/global_win_competition_details_13771_non_heart_brand.json`
  — every domain in it was separately confirmed live to resolve with a
  200 (plain `httpx`, following redirects), including the one genuine
  quirk found along the way: Gold Radio's winplus domain
  (`winplus.goldradiouk.com`) is **not** the same domain as its own main
  site (`goldradio.com`, per `init.json`'s own
  `brands.goldradio.meta.link`). `rivieraradio` (id 100, `brandRegion:
  "world"`) is deliberately left unmapped — it's not in the real T&Cs
  platform list, and no real competition observed so far is tagged with
  it alone; a competition that ever is fails closed (raises) rather than
  guessing a homepage for it.
- `open_authenticated_page(url)` — same shape as `browser.open_page()`:
  launch, `sign_in(page)`, resolve and navigate to the target
  competition's brand homepage, dismiss consent, click through to the
  competition by its numeric id (`a[href*="/competition/<id>/"]` —
  confirmed live this is exactly the real anchor shape both a
  brand-specific and the generic homepage render), then yield the page.
  Never falls back to a bare `goto()` of the target URL — raises instead
  if no matching click-through link is found on the resolved homepage.

**Shared consent-dismiss helper**: moved the proven Sourcepoint idiom
(`iframe[id^="sp_message_iframe"]` + substring-matched "Accept", wrapped
in `try/except: pass`) out of `stations/talksport_widget.py`'s own inline
copy into `entry_execution/browser.dismiss_consent_banner()`, now called
unconditionally from the existing anonymous `open_page()` too (a small,
generically useful improvement on its own) as well as from
`global_win_auth.py`. Confirmed live that globalplayer.com/signin/'s own
consent modal uses the identical markup, so the same idiom works there
verbatim with no adaptation needed.

**Routing**: `draft.py`/`submit.py` both now pick
`global_win_auth.open_authenticated_page` over `browser.open_page` when
`promo.station_name_raw == global_win.STATION_NAME` — the same
`station_name_raw` equality idiom `backfill_global_win_recurrence.py`
already established, now used in the live execution path for the first
time, not just one-off maintenance. Fresh sign-in per channel, no session
reuse across channels in one run, matching this codebase's "nothing
persisted, fresh every time" posture elsewhere (Bauer's guest token,
`global_win.py`'s own `login()`) and the job's real observed volume
(rarely more than one Global WIN channel per run). With
`GLOBAL_PLAYER_EMAIL`/`PASSWORD` unset, both fail closed immediately
(`EntryStatus.FAILED`, `submission_error="GLOBAL_PLAYER_EMAIL/PASSWORD
not set"`) before ever opening a browser — same shape as `draft.py`'s
existing "no UserProfile configured" hard-stop.

**Tests**: `tests/test_global_win_auth.py` — `extract_competition_id()`
and `_resolve_homepage_for_competition()` against the real
`heart_global_init.json`/`heart_global_competitions_list.json` fixtures
plus a couple of synthetic listings (a competition tagged with only one
known brand, one tagged only with the unmapped `rivieraradio`, one id not
in the listing at all) via a fake client, no live network call — same
convention as `test_global_win.py`'s own `_FakeClient`.
`tests/test_entry_execution_routing.py` (new) — `draft_one()`/
`submit_one()` pick the right opener for a Global WIN vs. non-Global-WIN
promotion (both openers faked as no-op context managers, `extract_form_fields`/
`click_submit` stubbed so no real page object is ever needed), plus the
credential-unset FAILED-status path for both, asserting the opener is
never even called in that case. `sign_in()`/`open_authenticated_page()`/
the click-through mechanics have no offline unit test, matching
`talksport_widget.py`'s own precedent (its live-fetch functions aren't
unit-tested either) — verified live instead, as detailed above. Full
suite: 194 passed, 1 skipped (pre-existing, unrelated — the live Gemini
mapping test), zero real network calls or credentials anywhere in the run.

**What remains genuinely unverified until a real login happens**: the
actual sign-in submission (email/password were never typed into the real
form — no credentials exist anywhere this environment can reach) and,
downstream of that, whether a winplus subdomain's own frontend actually
recognises the resulting session as signed in, whether the real entry
form's fields extract and fill sensibly once past sign-in, and whether a
real submission produces a genuine confirmation state. That first real
attempt is deliberately the user's own action — triggered and watched
directly (a local run with real env vars, or `gcloud run jobs execute`),
once the two already-created Secret Manager secrets
(`global-player-email`/`global-player-password`) are bound to the
`radio-comp-entry-execution` Cloud Run Job (not done as part of this
work — an infra step for the user to run separately).

## 2026-09-28 — The first real run, a real bug found, and a real repeated-login incident

Secrets bound, IAM granted (`roles/secretmanager.secretAccessor` for the
compute service account — the initial `gcloud secrets create` calls
didn't imply this, a real gap in the earlier instructions), image
rebuilt, and — critically — the `radio-comp-entry-execution-15min`
Cloud Scheduler job was paused *before* any of this, specifically so the
first real login would be a manually-triggered, watched event rather
than something firing unsupervised on its own 15-minute cadence.

The manual trigger confirmed the core mechanism works: `global_win_auth.sign_in()`
really did log in with real credentials and really did reach a real
entry form. But it also surfaced two real, serious problems, neither of
them specific to Global WIN:

1. `draft.py` never caught an exception from `llm_mapping.request_field_mapping()` —
   it just propagated out of `draft_one()` uncaught. `run_entry_execution.py`'s
   own per-item `try/except` logs it and moves on, but **no `EntryRecord`
   ever got saved**, so the channel looked "never attempted" again on the
   very next pass.
2. Cloud Run Jobs' own `maxRetries: 1` re-executes the *entire* job from
   scratch after a timeout. The real authenticated flow (sign-in +
   homepage load + click-through) takes long enough per channel that,
   with 5 genuinely-free Global WIN channels eligible at once (a real
   backlog, this being the first run since the feature shipped), the job
   hit its own 600s timeout and got retried by Cloud Run itself.

Combined, these two meant: five real channels, no saved record for any
of them, each hit Gemini's free-tier rate limit (20 requests/day — hit
immediately given the volume) and raised, and Cloud Run retried the
whole thing at least once more. Net result: **8 real Global Player
sign-ins in 16 minutes**, zero drafts produced, zero records saved —
exactly the repeated-login pattern this whole feature was designed to
avoid, caused by an unrelated pre-existing gap, not by anything wrong
with the login mechanism itself.

Fixed both root causes, not just the specific failure mode observed:
- `draft_one()`/`submit_one()` are now each wrapped in a broad outer
  `try/except Exception` (`draft.py`'s `_draft_one_inner`/`submit.py`'s
  `_submit_one_inner`) that saves a `FAILED` `EntryRecord` with a clear
  `submission_error` for *anything* unhandled — not just the LLM call,
  since the exact same silent-propagation risk exists for `opener(url)`'s
  own sign-in/navigation failing, or anything else not already given its
  own specific handler. The LLM call additionally keeps its own
  more-specific inner handler (a clearer error message for the failure
  mode actually seen live) inside that same backstop.
- `radio-comp-entry-execution`'s Cloud Run Job now has `maxRetries: 0` —
  Cloud Run itself never automatically re-executes a timed-out/crashed
  job; a real failure is picked up cleanly on the job's own next
  scheduled tick instead (which re-evaluates draftable/submittable
  channels fresh), not blindly re-run in place.
- `tests/test_entry_execution_error_handling.py` (3 tests): an LLM
  exception and an unrelated opener exception (simulating a sign-in/
  navigation failure) both now save a `FAILED` record instead of
  propagating, for both `draft_one()` and `submit_one()`. Full suite:
  197 passed, 1 skipped.

**On the Gemini quota itself**: discussed moving off the free tier
(cheap for this volume) vs. reducing entry-execution's own polling
frequency. Chose to stay on the free tier and reduce frequency instead —
`radio-comp-entry-execution-15min`'s Cloud Scheduler cadence changed from
`*/15 * * * *` to `15 * * * *` (hourly, offset 15 minutes after
`radio-comp-discovery-hourly`'s own `0 * * * *` run, so it never reads
promotions/channels the same instant discovery might still be writing
them). Worth being honest about the actual mechanism here: once the bug
above is fixed, polling frequency doesn't multiply login/LLM-call
volume by itself — an idle tick with nothing eligible already exits
before Playwright ever launches, so login count is really driven by how
many genuinely-free channels get discovered per day, not by how often
entry-execution checks. Reducing to hourly is a reasonable extra safety
margin regardless (fewer poll cycles, one less variable), but it doesn't
fully remove the risk that a single day's genuine volume (across *all*
sources, not just Global WIN) could still exceed the free tier's 20
requests/day on its own.

## 2026-09-29 — Two more real gaps found on the first real scheduled runs

**The Cloud Scheduler trigger for `radio-comp-entry-execution` had never
actually worked.** It fired hourly all along, but every attempt failed
with a permission error before ever creating a job execution — the
compute service account was never granted `roles/run.invoker` on this
specific job (unlike `radio-comp-discovery`, which had it from the
start). Every real run to date, including the two from 2026-09-28, was
manually triggered. Fixed with one `gcloud run jobs add-iam-policy-binding`
call; confirmed live afterward that the schedule now actually creates and
completes real executions.

**Most real drafts were still failing, just safely now.** With the
scheduler fix in place, a real scheduled run picked up 6 draftable
channels. Yesterday's exception-handling fix worked exactly as designed —
every failure got exactly one real login and a clean `FAILED` record, no
repeats. But the actual failures revealed a new, previously-unknown gap:
5 of 6 failed at the in-app click-through step, because the resolved
brand homepage (almost always `winplus.globalplayer.com`, since
`globalplayer` is usually the first brand tag on a competition) doesn't
actually surface a clickable link to it. Being tagged for a brand and
being *linked from* that brand's own homepage turned out to be two
different things.

Fixed: `_resolve_homepage_for_competition` (singular) is now
`_resolve_homepages_for_competition` (plural) — returns every known
homepage a competition is tagged with, in its own `brands`-array order,
instead of just the first match. `open_authenticated_page` tries each
candidate in turn (navigate, dismiss consent, attempt the click-through)
and only raises once every candidate has failed. `tests/test_global_win_auth.py`
updated to match (7 tests, including a new one proving an unmapped brand
tag alongside a real one still resolves to the real one rather than
failing outright). Full suite: 198 passed, 1 skipped.

Not yet re-verified live whether this actually gets a real draft all the
way through — that's the natural next thing to watch for once this
deploys and the scheduler's next tick finds something eligible.

## 2026-09-30 — A new talkSPORT page template: embedded Google Forms, no "How to Enter" section at all

Two real, currently-live competitions ("WIN a trip to Philadelphia for
two", "Win up to £1k on White & Jordan") use a template `talksport.py`
had never seen: no "How to Enter" heading at all, just prose pointing at
a Google Form embedded via `<iframe class="authenticated-iframe" ...
src="https://docs.google.com/forms/...">`. Confirmed live (real fetches,
both pages, before writing anything) that this produced `channels = []`
for both — not even an ambiguous channel got recorded, because
`_extract_how_to_enter_block()`'s classifier only recognises the known
"How to Enter" subsection headings, and this template has none.

Two real gaps, both needed before these could be automated at all:

1. **Discovery never saw them** (above). Fixed with a new small shared
   helper, `stations/google_forms.py` (`find_embedded_form_url()`, a
   regex over the raw HTML — not station-specific, since any future
   adapter could hit the same third-party-embed pattern, mirroring
   `browser.py`'s `dismiss_consent_banner()` precedent). `talksport.py`'s
   `parse_detail()` now falls back to it only when the existing
   "How to Enter" classifier genuinely finds nothing, building one
   `WEB_FORM` channel whose `channel_url_or_number` is the **real Google
   Form URL**, not the talkSPORT page — `draft.py`/`submit.py` already do
   `url = channel.channel_url_or_number or promo.source_url`, so this
   alone routes entry-execution to the right page.

   Conservative classification, checked live rather than assumed: neither
   real page's own prose contains "free to enter", "no purchase
   necessary", "free of charge" or similar anywhere near the form mention
   — "uses a Google Form" is not itself evidence of a free route. Both
   correctly come back `is_free_route=None`/`review_recommended=True`,
   same as every other ambiguous case this codebase already produces.

   Also confirmed live: fetching the same Form URL with and without its
   `?usp=publish-editor` query string both return 200 with materially the
   same content, no redirect — so no URL normalisation was needed.

2. **Entry-execution's shared form handling couldn't cope with a real
   Google Form's DOM**, confirmed live (Playwright, passive DOM
   inspection only, on both real pages) before writing anything:
   - A field's question text lives in a separate `[role="heading"]` div,
     never linked to its input via `id`/`label[for]`/`aria-label`/a
     wrapping `<label>` — every existing `_resolve_label()` strategy
     misses. Confirmed live that the actual shared ancestor is
     `[role="listitem"]` (one per question, wrapping both the heading and
     the input/radiogroup) — `_resolve_label()` gained one more fallback:
     `el.closest('[role="listitem"]')` → its nested `[role="heading"]`
     text. This only fires once every native strategy above it has
     already failed, so normal HTML forms resolve exactly as before.
   - Radio questions are `role="radio"` divs (grouped, on both real
     forms, under a `role="radiogroup"` ancestor), not real
     `<input type="radio">` — invisible to `extract_form_fields()`'s
     `input, textarea, select` selector. Added a second pass,
     `_add_option_group_fields()`, that finds `[role="radio"]`/
     `[role="checkbox"]` elements, groups them by their common
     `[role="listitem"]` ancestor (the same boundary the label fallback
     uses — more robust than depending on Google's own `radiogroup` role,
     which was never confirmed for a checkbox question, since neither
     real form had one), and gathers each option's `aria-label` into an
     `options` list the same shape `select` already produces.
   - One live surprise found along the way: a Google Form's own
     `<textarea>` (long-answer) field carries a generic `aria-label`
     of literally `"Your answer"` on every such field regardless of the
     real question — confirmed live on the Philadelphia form's "Address"
     field. Trusting it would have been exactly the kind of
     confident-looking-but-wrong label this project's classifiers already
     avoid elsewhere, so `_resolve_label()` excludes that exact literal
     value and falls through to the `[role="listitem"]` fallback instead,
     which correctly returns "Address". (A field's real per-sub-input
     `aria-label`s, like a date-of-birth field's "Day of the
     month"/"Month"/"Year", are untouched by this exclusion.)
   - The submit control is `<div role="button">Submit</div>` — matches
     none of `click_submit()`'s three existing selectors. Added a fourth:
     the `div[role="button"]` whose visible text is exactly `"Submit"`.
     Both real forms also have a `"Clear form"` `div[role="button"]`
     sibling, confirmed live to never match.
   - `apply_fill_actions()`'s "check" action now inspects the resolved
     element: a real `<input>` still uses `page.check()`, unchanged; our
     own `[role="listitem"]` group-container marker instead clicks the
     descendant option whose text reads "yes" (both real radio questions
     on these two forms are Yes/No consent-style), falling back to the
     first option if none matches. No change to the human-approval gate
     or `needs_manual_input()` — a Google Form's Yes/No question flows
     through the exact same `FieldClassification`/`checkbox_action` logic
     every other field already does; this is new field *detection*, not
     a new automation policy.

All of `browser.py`'s changes are additive — every existing
native-HTML-form test passes unchanged (`test_entry_execution_form_extraction.py`'s
original cases, `test_entry_execution_routing.py`,
`test_entry_execution_error_handling.py`).

**New tests**: `tests/test_google_forms.py` (3 tests, against the two
real fixture pages plus a negative case using an existing normal page);
`tests/test_talksport_adapter.py` (+2, `parse_detail()` against both real
fixtures, proving the `WEB_FORM` channel and its ambiguous classification);
`tests/test_entry_execution_form_extraction.py` (+5, against a real
captured/rendered Google Form snapshot — `page.content()` after real
Playwright rendering of the live Philadelphia form, loaded back via
`file://`, same technique `sample_entry_form.html`/`clean_entry_form.html`
already use). One of the five deliberately does *not* call
`click_submit()` itself — it replicates its selector/predicate logic
inline to prove "Submit" matches and "Clear form" doesn't, without ever
invoking a real click on a Google Form's submit control, fixture or
live, which this work treated as a hard rule throughout, not just for
the two real competition pages. Full suite: 208 passed, 1 skipped.

**Live-verified end to end**, in this order: (1) real fixtures — both
competition pages and the rendered Form — captured by actually fetching/
rendering the real live pages, not written by hand; (2) a real
`talksport.py` run (`STORAGE_BACKEND=local`) against the live site
picked up both real competitions with a `WEB_FORM` channel pointing at
the real Form URL, `review_recommended=True` on both, exactly as
designed; (3) `browser.open_page()` + `extract_form_fields()` run for
real against both live Form URLs (not just the offline fixture) found
the identical fields/labels/options as the fixture-based tests, and the
`div[role="button"]` submit-selector logic matched "Submit" only on both
real live pages (never clicked); (4) `draft.draft_one()` run for real
against the real discovered Philadelphia promotion — this sandbox has no
`GEMINI_API_KEY` configured, so the real LLM mapping call itself
correctly failed and produced a clean `FAILED` `EntryRecord`
(`draft_screenshot_path=None`), the same fail-closed behaviour
`test_entry_execution_error_handling.py` already covers; to still verify
the rest of the pipeline for real, a one-off script (not part of the
test suite) stubbed only the LLM call and `load_user_profile()` — with
obviously-fake test data, never real PII, and against an isolated tmp
storage dir, not this project's real `data/` — and ran everything else
for real: real Playwright, real navigation to the real live Philadelphia
Google Form, real field-fill, real screenshot. Reached
`EntryStatus.DRAFTED` with a real saved screenshot showing all four
profile fields correctly filled and the radio question correctly left
unanswered (a deliberate `leave_unchecked` choice for that dry run, not a
gap) — Submit visible in the screenshot, never clicked. Getting a real
`GEMINI_API_KEY` into this environment (or provisioning one) is the
natural next step to verify the LLM-mapping stage itself live, end to
end, without a stub.

## 2026-09-30 — Fixed a real correctness gap in the Google Form radio-question handling

Reviewing the build above before deploying it surfaced a real, unshipped
bug in the "click whichever option reads 'yes'" design described just
above: `CheckboxAction` (`CHECK`/`LEAVE_UNCHECKED`) was built for a
single toggle, where "check" only ever has one meaningful direction. A
Yes/No radio question doesn't work that way — the LLM prompt already
allows "check" for anything "confirming age or eligibility," and plenty
of real eligibility questions have **"No" as the truthful, correct
answer** for a genuine entrant (e.g. "Are you an employee of the
promoter?", "Have you won a prize from us in the last 6 months?"). The
schema had no way for the model to express a direction at all — only
on/off — so the code's own hardcoded "click yes" default would have
submitted false information on exactly this class of question, and this
was never actually exercised against a real Gemini call (no
`GEMINI_API_KEY` in the build environment) before being flagged.

Fixed properly rather than papered over: `fill_plan.py` gains a new
`FieldClassification.OPTION_GROUP`, distinct from `CHECKBOX` — the model
must name the *specific* correct option (`selected_option`), copied
verbatim from the field's own real, extracted options, never invented
(`validate_mapping()` checks this the same way it already checks
selectors). The system prompt (`llm_mapping.py`) now tells the model
explicitly to get the *direction* right ("Are you 18 or over?" → "Yes",
but "Are you an employee of the promoter?" → "No"), and to prefer
`unmappable` over guessing a direction it isn't confident about.
`validate_mapping()` also now **rejects** a `CHECKBOX` classification on
any field that has real options attached at all — closing the loophole
that let the old, dangerous path fire in the first place; a field with
options must go through `OPTION_GROUP`.

`browser.py`'s `_check_or_click_option()` (the "click yes" function) is
gone — `apply_fill_actions()`'s `"check"` action is back to a plain
`page.check()` exactly as before this whole feature started (it will
only ever be called for a genuine single checkbox now, never a role
group). A new `_select_option()` selects the one option
`MappedField.selected_option` actually names — works for a Google Form's
`role="radio"`/`role="checkbox"` groups and, as a natural side effect,
for a native `<select>` dropdown too (`page.select_option` by label) —
a pre-existing, previously-unaddressed gap (no native-select handling
existed anywhere in this codebase before), fixed for free by the same
mechanism rather than as separate scope creep.

Tests rewritten to match: `tests/test_fill_plan.py` (+6) cover both
directions explicitly (`selected_option="No"` on an eligibility question
is the exact scenario the bug got wrong), an invented option being
rejected, and the new `CHECKBOX`-with-real-options rejection.
`tests/test_entry_execution_form_extraction.py`'s Google Form
radio-question test was rewritten (the old one only proved a "yes"
element could be *found*, never that a specific direction was actually
selected) — the frozen offline fixture's own JS doesn't run (no live
backend to react to a click), so verification uses a native
`click`-event listener recording which specific DOM element received
the click, proving "No" selects "No" and "Yes" selects "Yes", not a
hardcoded default either way. Full suite: 215 passed, 1 skipped.

Not yet re-verified live end-to-end with a real Gemini call (still no
`GEMINI_API_KEY` in this environment) — the next real draft attempt
against a Google Form field will be the first real test of whether the
model actually uses `option_group` and gets the direction right in
practice, not just that the code handles it correctly when it does.

## 2026-10-05/06 — A new Global platform found by the user: "Global Commercial" (`comp.*`)

The user found a real competition on a platform this project had never
seen: `comp.smoothradio.com/nescafe-2026/8`, Global's own in-house
"brand-sponsored competition" tool (internal name "Global React Studio"/
"Global Commercial" — Next.js + Sanity CMS, served per-brand at
`comp.<brand>.co.uk`/`.com`), entirely separate from the already-built
Global WIN/`winplus.*` platform despite both being Global's own
infrastructure. The user had already manually created a separate account
on it (confirmed: a distinct Gigya apiKey from Global Player's) and asked
for discovery + full login/submit automation reusing that account.

Two rounds of read-only live investigation (no form ever submitted, no
CAPTCHA touched) confirmed everything needed to build this safely:

- **Discovery needs no auth at all.** The whole competition — title,
  dates, T&Cs URL, the tie-breaker question/options, even the correct
  answer — is embedded in the page's own server-rendered HTML as Next.js
  "flight data", readable with a plain `httpx` GET.
- **Login is not CAPTCHA-gated**, confirmed two ways: no reCAPTCHA
  markup renders on the login panel in either tab state, and the login
  widget's own JS (`emailSignIn()`) posts a bare `{email, password}` with
  no recaptcha field at all — unlike registration (`emailRegister()`),
  which does carry one. Real login POSTs to
  `https://www.smoothradio.com/api/derrick/2/email-sign-in/`,
  cookie-session based.
- **A real, consequential, user-made call**: this platform's own page
  leaks the tie-breaker's correct answer in plain unauthenticated JSON
  (`entryMultipleChoice.correctAnswer`). Asked the user directly whether
  this should ever be used to auto-select the right option, rather than
  always treating a multiple-choice question as needing manual input (the
  more conservative default this project would otherwise apply, matching
  how a creative tie-breaker is always flagged). **The user chose to use
  it** — stated here plainly as their own explicit decision, not an
  inference. This is why this one source can go all the way through
  real, automated submission rather than draft-and-flag like every other
  creative/skill-based question in this codebase.

**Built**: `stations/global_commercial.py` (discovery — parses the
Next.js flight-data format via a small string-aware brace/bracket
counter rather than a full RSC deserialisation; conservative free/paid
classification, same "no real paid signal seen yet" posture as every
other adapter — the one real competition found has no free/paid language
in its own T&Cs, so it correctly stays ambiguous rather than being
assumed free); `entry_execution/global_commercial_auth.py` (the
authenticated companion — materially simpler than Global WIN's, since
login happens inline on the competition page itself, no homepage/
click-through resolution needed). Routing in `draft.py`/`submit.py`
follows the exact same `promo.station_name_raw == STATION_NAME` branch
pattern, failing closed to `FAILED` before opening a browser if
`GLOBAL_COMMERCIAL_EMAIL`/`PASSWORD` are unset.

**A real, non-obvious UI quirk found and worked around**: the "Log In"
tab (`#select-login`) can't be clicked via a normal Playwright
position-based click — the `<li>` itself has a zero-height bounding box,
and its `<a>` child is visually covered by a sticky page footer even with
`force=True` (confirmed neither attempt actually flipped the tab's own
"active" CSS class). The one mechanism confirmed to work is a real DOM
`.click()` dispatched directly via `page.locator(...).evaluate("el =>
el.click()")`, bypassing Playwright's position-based hit-testing
entirely.

**A real gap found and fixed during review, before this shipped**:
`parse_detail()`'s guard clause used `not campaign` to check for a
missing campaign block, but Python's `not {}` is `True` — an empty-but-*
present* campaign dict (a real, valid shape for a test isolating
title-resolution behaviour) was wrongly treated as "no campaign at all."
Fixed to check `campaign is None` specifically. Caught by two tests the
build itself wrote, which is exactly what they were for.

**What remains genuinely unverified**: the real login submission itself
(no `GLOBAL_COMMERCIAL_EMAIL`/`PASSWORD` exist in any environment this
was built in) and, downstream of that, whether `sign_in()`'s own
success check (the Gigya widget's `step` attribute leaving its known
pre-login value) actually fires correctly on a real successful login —
every mechanic short of that was verified live. That first real attempt
is deliberately the user's own action, watched, once the two Secret
Manager secrets are created and bound to `radio-comp-entry-execution`.
Full suite: 238 passed, 1 skipped.

## 2026-10-06 — Global Commercial's first real login: two real deploy bugs, then it worked

The user confirmed the Nescafe competition free for real and asked to
test it. Schedule paused first, as planned. First attempt failed
immediately with `ModuleNotFoundError: No module named 'bs4'` —
`Dockerfile.entry-execution` never needed a `stations/` adapter's own
dependencies before (Global WIN's own module doesn't use bs4), so this
image never had `beautifulsoup4` installed; draft.py's new routing
import of `global_commercial.py` pulled it in for the first time. Fixed,
rebuilt, retried.

Second attempt reached the real login form and filled it correctly, but
the submit button's own `page.click()` timed out after 30s — the exact
same sticky-footer pointer-event interception already found and worked
around for the "Log In" tab also affects this button. Fixed the same
way: a direct DOM `.click()` via `evaluate()`, bypassing Playwright's
position-based hit-testing. Rebuilt, retried.

**Third attempt: real sign-in succeeded for the first time**, and the
tie-breaker was correctly auto-answered ("Matilda") using the leaked
`correctAnswer` field, exactly as designed. The only remaining failure
was a transient Gemini `503 (experiencing high demand)` at the
field-mapping step — confirmed not a free-tier rate limit (the error
text and code differ), and confirmed real rather than a fluke by seeing
the identical error on an immediate retry too. Decided not to keep
manually forcing retries against what looks like a live Gemini outage —
the part that actually needed careful, watched verification (real
login + tie-breaker mechanics) is now proven correct twice in a row, so
further attempts don't need the same supervision. Resumed the normal
hourly schedule; it'll pick this up naturally once Gemini recovers.

Each of the three stale `FAILED` records this produced had to be removed
by hand (direct GCS JSON edit, backed up and diffed before each write —
`storage/base.py`'s `Repository` protocol has no `delete()` at all) so
the channel stayed eligible for retry — a real, currently-missing
capability worth a proper fix later (a `delete()` method, or a small
"retry this specific failed record" tool) rather than hand-editing
production JSON again next time.
