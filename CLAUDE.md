# CLAUDE.md

Context for Claude Code working in this repo. Read this file first, every
session — it's the handoff from the design/scoping work that happened
before this repo existed in VS Code.

## What this project is

A personal automation system for Adán to discover and (eventually,
semi-automatically) enter UK radio phone-in/text-in competitions. The
premise, from a friend who worked at Radio X: relatively few people enter
these competitions, so the expected value per entry may be better than it
looks. This repo is the implementation of that idea, built out in phases
with explicit sign-off between each one.

Full background lives in `docs/`:
- `docs/scoping-research.md` — the research phase: legal framework, the
  competition landscape, evidence for/against the "few entrants" hypothesis,
  and a Fermi/sensitivity model estimating expected annual prize value
  (revised base case ~£1,374/year after accounting for the anecdote coming
  from a large station, Radio X, rather than a typical one).
- `docs/technical-specification.md` — the full technical spec: architecture,
  discovery engine, compliance engine, entry-execution engine, notification
  layer, tracking, data model, stack choices, GCP hosting plan, build
  phases, open risks.
- `docs/build-log.md` — chronological log of what's actually been built,
  in what order, and why, including bugs found and fixed along the way.

Read the spec before making architectural changes, and the build log
before assuming something isn't built yet — check there first.

## Non-negotiable design constraints

These came out of explicit decisions earlier in the project and should not
be silently relaxed by future changes, however convenient it might seem:

- **Single real identity only.** `UserProfile` is deliberately a singular
  model, not a collection. No multi-identity, no VPN/proxy tricks, no
  bulk-entry code paths of any kind. This system enters competitions as
  Adán, once, like any other entrant.
- **No automation of any phone channel — full stop.** This includes live
  on-air call-ins (`ON_AIR_CALL_IN`) and automated non-live entry lines
  (`PHONE_ENTRY`, e.g. "call this number and follow the prompts," including
  "free phone entry" IVR routes). Both are tracked for visibility only and
  must never be auto-dialled. This was an explicit scope decision (excluding
  live call-in entirely), not an oversight — don't build a phone-automation
  path even for the "free" phone routes.
- **Conservative channel classification, always.** When an `EntryChannel`
  can't be classified with confidence as free or paid from the source text,
  it must come back `is_free_route=None` with `review_recommended=True` —
  never a guessed value. This is what gates the entry-execution engine;
  don't loosen the classifier's confidence bar to reduce the review queue.
- **Conservative value extraction, always.** Prefer `prize_value_gbp=None`
  over a wrong-but-confident-looking number. (Real bug hit during Phase 0:
  a body-text fallback picked up an SMS entry cost as the "prize value.")
- **Human-in-the-loop by default**, especially for anything creative or
  skill-based (tie-breaker questions, "in 25 words or fewer," etc.) — the
  entry-execution engine drafts, it doesn't submit unattended, unless a
  future phase explicitly revisits that with the user.
- **Gambling-law compliance matters.** Entries should use genuine free
  entry routes (UK Gambling Act 2005 s.14: equal cost, equal prominence,
  same prize pool as the paid route) rather than working around them. Pay
  attention to Ofcom Broadcasting Code fairness rules (2.13–2.16) and
  premium-rate disclosure (10.9–10.10) if the compliance engine gets built
  out further.

## Current state (as of this handoff)

- **GCP project:** `project-a6778446-201f-4aa5-a03` ("Comp Enterer"), £2
  budget alert set. `gcloud` API-enable + Firestore-create steps are in
  `README.md` — check with the user whether these have been completed yet;
  as of this handoff the codebase still defaults to `STORAGE_BACKEND=local`
  (JSON files under `data/`), not Firestore.
- **GitHub:** `https://github.com/as-far-as/comp-enterer` (private), pushed
  and live. If push/auth ever needs redoing, VS Code's Source Control panel
  → "Publish Branch" (proper OAuth flow) worked; manual token/keychain
  handling did not — see `docs/build-log.md` for the full story.
- **Built and tested (7/7 tests passing):**
  - `src/radiocomp/models.py` — full Pydantic data model.
  - `src/radiocomp/storage/` — `local_json.py` (default, working) and
    `firestore_store.py` (written, not yet exercised against real GCP).
  - `src/radiocomp/aggregators/loquax.py` — working Loquax discovery
    adapter, with same-run dedup for a real duplicate-listing bug found
    in testing.
  - `src/radiocomp/stations/talksport.py` — working direct-station
    monitor for talkSPORT, using plain `httpx` (Playwright turned out not
    to be needed here — check per-station before reaching for it).
  - `tests/` — offline tests against saved real HTML fixtures.
- **Not built yet** (see `docs/build-log.md` for the fuller list): a second
  aggregator adapter (theprizefinder), the Ofcom station-directory
  seed/workaround, a second direct-station monitor that actually needs
  Playwright, T&C snapshot capture + compliance engine, Cloud Scheduler →
  Cloud Run Job wiring.

## Prioritized next steps

1. Confirm the remaining `gcloud` setup is done (enable APIs, create
   Firestore database) for `project-a6778446-201f-4aa5-a03`, then wire
   `STORAGE_BACKEND=firestore` + `GCP_PROJECT_ID` via `.env` and test the
   storage layer against real Firestore.
2. Second aggregator adapter: `theprizefinder.com`, same pattern as
   `loquax.py`.
3. Resolve the Ofcom licensed-stations dataset gap (URL couldn't be found
   in the original research session — try `data.gov.uk` or Ofcom's current
   site structure), or seed `Station` records manually for a first tranche
   of local/independent stations.
4. A second direct-station monitor, ideally for a site that actually needs
   Playwright, so the "plain httpx vs. real browser" judgement call gets
   tested against a second real case.
5. `TandCSnapshot` capture + a first-pass compliance engine (spec section
   4) — the models and `EntryChannel.review_recommended` flag already
   support this; the clause-diffing logic itself isn't built.
6. Wire Cloud Scheduler → Cloud Run Job for scheduled runs, once the GCP
   side is confirmed ready.

## Working conventions so far

- Adapters are tested against saved real HTML fixtures (`tests/fixtures/`),
  not mocked-up sample HTML — this is what caught both real bugs so far
  (a Loquax duplicate-listing quirk, a talkSPORT prize-extraction
  misfire). Keep doing this for new adapters.
- Prefer plain `httpx` + BeautifulSoup by default; only reach for
  Playwright when a specific site actually needs JS rendering or defeats
  a plain fetch — don't assume it's needed up front.
- When in doubt between a confident-but-possibly-wrong extraction and a
  `None` + review flag, take the `None`. This shows up repeatedly in the
  code and should stay the default posture for any new adapter.
