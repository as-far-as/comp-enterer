"""
Data model — mirrors section 8 of the technical spec exactly, as Pydantic
models. Each class here becomes one Firestore collection (UserProfile is
the one exception: a single document, not a collection, by design — see
its docstring).

These models are storage-agnostic on purpose. Nothing in here imports
Firestore or knows about GCP; the storage layer (storage/) is what maps
these to either a local JSON file or a real Firestore collection,
depending on config.STORAGE_BACKEND. That's what lets the discovery and
compliance logic be written and tested today, before the GCP project
exists.
"""

from __future__ import annotations

import uuid
from datetime import datetime, date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class EntryChannelType(str, Enum):
    WEB_FORM = "web_form"
    SMS = "sms"
    APP = "app"
    POST = "post"  # free-route-by-mail — tracked for visibility only, this system can't post a letter for you
    PHONE_ENTRY = "phone_entry"  # an automated non-live entry line (e.g. "call this number, follow the prompts") —
    # distinct from ON_AIR_CALL_IN below, but still a phone channel, so it gets the same treatment: notify-only,
    # never auto-dialled, consistent with excluding all phone automation per the spec's decision, not just the
    # live-broadcast case that decision was originally about
    ON_AIR_CALL_IN = "on_air_call_in"  # tracked for visibility only — never auto-entered, see spec section 5
    EMAIL = "email"  # "send your name and number to studio@..." — observed live on stations/radioexe.py
    WHATSAPP = "whatsapp"  # "message your answer on WhatsApp <number>" — same discovery as EMAIL above; neither
    # was anticipated by the original spec, and no automation path touches either, so they're modelled for
    # accurate classification/review purposes only, not as a target for future auto-entry


class DiscoveredVia(str, Enum):
    AGGREGATOR = "aggregator"  # e.g. Loquax, theprizefinder
    DIRECT = "direct"  # station's own site, monitored directly


class Station(BaseModel):
    """One radio station or network. Seeded initially from the networks
    the research already mapped (Global, Rayo/Bauer, talkSPORT). The
    local/independent tier was meant to be seeded from Ofcom's licensed-
    stations register, but no current bulk/downloadable version of that
    register turned out to exist (see docs/build-log.md, 2026-09-02) — so
    stations/seed_local_independent.py seeds a manually-picked, live-checked
    first tranche instead. ofcom_licence_ref stays unset for anything from
    that seed; it's not Ofcom-sourced data."""

    id: str = Field(default_factory=_new_id)
    name: str
    network: Optional[str] = None  # e.g. "Global", "Rayo/Bauer", "talkSPORT", or None if fully independent
    ofcom_licence_ref: Optional[str] = None
    base_urls: list[str] = Field(default_factory=list)
    is_local_independent: bool = False  # drives Tier D discovery-priority logic later
    notes: Optional[str] = None


class Promotion(BaseModel):
    """One distinct competition run by a station/network."""

    id: str = Field(default_factory=_new_id)
    station_id: Optional[str] = None  # may be unresolved at ingestion time; normalizer fills this in
    station_name_raw: str  # exactly as seen at the source, before matching to a Station record
    network: Optional[str] = None  # drives cross-brand entry-limit checks (see compliance engine)
    title: str
    prize_description: Optional[str] = None
    prize_value_gbp: Optional[float] = None
    entry_deadline: Optional[date] = None
    discovered_via: DiscoveredVia
    source_url: str
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    dedup_hash: str  # hash of (station_name_raw, title, rough deadline) — see aggregators/_dedup.py
    recurrence_series_id: Optional[str] = None  # set only from a genuine source field confirming a
    # recurring series (e.g. Global WIN's competitionScheduleId when competitionIsRound is true) —
    # never inferred from title/date matching alone. notify/send.py uses this to send one message per
    # series rather than one per occurrence (see docs/build-log.md, 2026-09-28).


class TandCSnapshot(BaseModel):
    id: str = Field(default_factory=_new_id)
    promotion_id: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    raw_text: str
    raw_text_hash: str
    parsed_entry_limit: Optional[str] = None  # free-text note, e.g. "one entry per household per day"
    parsed_free_route_exists: Optional[bool] = None


class EntryChannel(BaseModel):
    id: str = Field(default_factory=_new_id)
    promotion_id: str
    channel_type: EntryChannelType
    is_free_route: Optional[bool] = None  # None = couldn't classify confidently; treat as NOT safe to auto-enter
    cost_to_entrant_gbp: Optional[float] = None  # 0.0 for free/standard-rate; premium-rate cost otherwise
    channel_url_or_number: Optional[str] = None
    review_recommended: bool = False  # set whenever automated extraction wasn't confident — see talksport.py
    raw_excerpt: Optional[str] = None  # the source text this classification was based on, for your own audit


class EntryStatus(str, Enum):
    DRAFTED = "drafted"  # compliance-cleared, form filled, awaiting your approval
    APPROVED = "approved"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"


class EntryRecord(BaseModel):
    """The audit trail. One row per entry the system has made (or drafted)
    on your behalf — this is what protects you if a station ever queries
    an entry, and what the EV model gets recalibrated against."""

    id: str = Field(default_factory=_new_id)
    promotion_id: str
    channel_type: EntryChannelType
    channel_id: Optional[str] = None  # the specific EntryChannel row, when known — a promotion can
    # have more than one channel of the same channel_type, and channel_type alone can't tell them apart
    status: EntryStatus = EntryStatus.DRAFTED
    drafted_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    compliance_note: Optional[str] = None  # which T&C clause/limit check cleared this entry

    # WEB_FORM two-stage flow only (entry_execution/) — see that package's
    # docstrings. Every other channel_type goes straight to APPROVED/SKIPPED
    # and never touches these.
    fill_plan: Optional[dict] = None  # the validated field mapping (selectors + classifications, never
    # literal PII values) saved at draft time and replayed unchanged at submit time — see
    # entry_execution/fill_plan.py. Literal values are re-derived from whatever UserProfile is
    # currently stored, not frozen here, since the mapping (not the values) is what needs to survive
    # unchanged between the two approval stages.
    draft_screenshot_path: Optional[str] = None  # e.g. "entry_screenshots/<id>_draft.png"
    submitted_screenshot_path: Optional[str] = None  # e.g. "entry_screenshots/<id>_submitted.png"
    submission_error: Optional[str] = None  # human-readable reason for a FAILED status — distinct
    # from compliance_note, which is about eligibility, not execution


class Outcome(BaseModel):
    id: str = Field(default_factory=_new_id)
    entry_id: str
    won: bool = False
    prize_claimed: bool = False
    claim_deadline: Optional[date] = None
    proof_required: Optional[str] = None  # e.g. "ID + voice match for on-air win"
    notes: Optional[str] = None


class UserProfile(BaseModel):
    """Deliberately singular — the schema has no concept of a second
    identity. See the compliance engine section of the spec for why."""

    name: str
    date_of_birth: date
    address: str
    phone: str
    email: str
