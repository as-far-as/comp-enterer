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
