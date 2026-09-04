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
