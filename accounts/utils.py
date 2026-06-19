"""Helpers for Discord account identity (F-UNIQ-07).

A Discord snowflake ID embeds the account creation timestamp, so we can
derive the account age without an extra API call.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# Discord epoch: 2015-01-01T00:00:00Z in milliseconds.
DISCORD_EPOCH_MS = 1420070400000


def discord_id_to_created_at(discord_id: str | int) -> datetime:
    """Return the UTC creation datetime encoded in a Discord snowflake ID."""
    snowflake = int(discord_id)
    milliseconds = (snowflake >> 22) + DISCORD_EPOCH_MS
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)


def discord_account_age(discord_id: str | int, *, now: datetime | None = None) -> timedelta:
    """Return how long ago the given Discord account was created."""
    now = now or datetime.now(tz=UTC)
    return now - discord_id_to_created_at(discord_id)


def is_discord_account_old_enough(
    discord_id: str | int, min_age_days: int, *, now: datetime | None = None
) -> bool:
    """Whether the account is at least ``min_age_days`` old (F-UNIQ-07)."""
    return discord_account_age(discord_id, now=now) >= timedelta(days=min_age_days)
