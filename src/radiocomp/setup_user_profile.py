"""
Run this yourself, in your own terminal — never through an AI agent's tool
calls. This collects your real name, date of birth, address, phone, and
email: a full identity record, not a revocable credential like the
Telegram bot token, so it deserves at least as much care about never
sitting in a conversation transcript or a tool-call log.

Writes to whatever STORAGE_BACKEND your .env currently points at (via
storage/user_profile_store.py) — set STORAGE_BACKEND=gcs first if you want
this reachable from the real Cloud Run Jobs, same as everything else.

Usage:
    python -m radiocomp.setup_user_profile          # set or replace your profile
    python -m radiocomp.setup_user_profile --check  # confirm one exists, without redisplaying it in full
"""

from __future__ import annotations

import sys
from datetime import date, datetime

from pydantic import ValidationError

from .models import UserProfile
from .storage.user_profile_store import load_user_profile, save_user_profile


def _prompt(label: str) -> str:
    value = input(f"{label}: ").strip()
    while not value:
        value = input(f"{label} (required): ").strip()
    return value


def _prompt_date_of_birth() -> date:
    while True:
        raw = input("Date of birth (YYYY-MM-DD): ").strip()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("  Didn't understand that — use YYYY-MM-DD, e.g. 1990-06-15.")


def _mask(value: str) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]


def check() -> int:
    profile = load_user_profile()
    if profile is None:
        print("No profile saved yet. Run `python -m radiocomp.setup_user_profile` to set one.")
        return 1
    print(f"Profile saved for: {profile.name}")
    print(f"  Date of birth: {profile.date_of_birth.year}-**-**")
    print(f"  Address:       {_mask(profile.address)}")
    print(f"  Phone:         {_mask(profile.phone)}")
    print(f"  Email:         {_mask(profile.email)}")
    return 0


def main() -> int:
    print("This sets the single profile the entry-execution engine will use to fill in forms.")
    print("Run this yourself — don't paste your details anywhere else, including into a chat with an AI agent.\n")

    while True:
        try:
            profile = UserProfile(
                name=_prompt("Full name"),
                date_of_birth=_prompt_date_of_birth(),
                address=_prompt("Address"),
                phone=_prompt("Phone number"),
                email=_prompt("Email address"),
            )
            break
        except ValidationError as exc:
            print(f"That didn't look right, let's try again:\n{exc}\n")

    save_user_profile(profile)
    print(f"\nSaved profile for {profile.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else main())
