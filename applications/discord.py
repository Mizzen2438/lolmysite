"""Discord Bot REST client and match-channel provisioning (F-DSC-05).

When a recruitment fills, the official Discord Bot creates a temporary,
private category containing a text and a voice channel that only the matched
participants can see, then issues an invite to the voice channel
(F-DSC-03/05, N-06). Only the REST API is used, so no always-on gateway
process is required — calls fit the stateless web service and a periodic
reconcile/cleanup command (see ``sync_discord_channels``).

Successful provisioning is recorded on the Recruitment so retries are
idempotent; created channel ids are stored so they can be torn down once the
session is over.
"""

from __future__ import annotations

import logging

import httpx
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Discord channel types.
CHANNEL_TEXT = 0
CHANNEL_VOICE = 2
CHANNEL_CATEGORY = 4

# Permission bits (https://discord.com/developers/docs/topics/permissions).
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
CONNECT = 1 << 20
SPEAK = 1 << 21
_MEMBER_ALLOW = VIEW_CHANNEL | SEND_MESSAGES | CONNECT | SPEAK

# Permission overwrite target types.
_OVERWRITE_ROLE = 0
_OVERWRITE_MEMBER = 1


class DiscordError(Exception):
    """Generic Discord API failure."""


class DiscordConfigError(DiscordError):
    """Bot token / guild id missing or invalid."""


class DiscordRateLimited(DiscordError):
    def __init__(self, retry_after: float = 1.0):
        self.retry_after = retry_after
        super().__init__(f"Rate limited; retry after {retry_after}s")


def _request(method: str, path: str, *, json: dict | None = None) -> dict | None:
    if not settings.DISCORD_BOT_ENABLED:
        raise DiscordConfigError("DISCORD_BOT_TOKEN / DISCORD_GUILD_ID が未設定です。")

    url = f"{settings.DISCORD_API_BASE}{path}"
    headers = {
        "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.request(method, url, headers=headers, json=json, timeout=10.0)
    except httpx.HTTPError as exc:
        raise DiscordError(f"Discord API への接続に失敗しました: {exc}") from exc

    if resp.status_code in (200, 201):
        return resp.json()
    if resp.status_code == 204:
        return None
    if resp.status_code == 404:
        # Channel already gone (e.g. deleted manually) — treat delete as done.
        if method.upper() == "DELETE":
            return None
        raise DiscordError("Discord リソースが見つかりません (404)。")
    if resp.status_code == 429:
        retry_after = float(resp.headers.get("Retry-After", "1"))
        raise DiscordRateLimited(retry_after)
    if resp.status_code in (401, 403):
        raise DiscordConfigError("Discord Bot トークンまたは権限が不正です。")
    raise DiscordError(f"Discord API エラー (status {resp.status_code}): {resp.text[:200]}")


def _everyone_deny_overwrite() -> dict:
    """Hide the channel from everyone by default (private channel)."""
    # The @everyone role id equals the guild id.
    return {"id": str(settings.DISCORD_GUILD_ID), "type": _OVERWRITE_ROLE, "deny": str(VIEW_CHANNEL)}


def _member_overwrites(discord_ids: list[str]) -> list[dict]:
    return [
        {"id": str(did), "type": _OVERWRITE_MEMBER, "allow": str(_MEMBER_ALLOW)}
        for did in discord_ids
        if did
    ]


def create_channel(
    name: str,
    channel_type: int,
    *,
    parent_id: str | None = None,
    overwrites: list[dict] | None = None,
) -> dict:
    payload: dict = {"name": name[:100], "type": channel_type}
    if parent_id:
        payload["parent_id"] = str(parent_id)
    if overwrites is not None:
        payload["permission_overwrites"] = overwrites
    return _request("POST", f"/guilds/{settings.DISCORD_GUILD_ID}/channels", json=payload)


def create_invite(channel_id: str, *, max_age: int, max_uses: int = 0) -> str:
    data = _request(
        "POST",
        f"/channels/{channel_id}/invites",
        json={"max_age": max_age, "max_uses": max_uses, "unique": True},
    )
    return f"https://discord.gg/{data['code']}"


def delete_channel(channel_id: str) -> None:
    _request("DELETE", f"/channels/{channel_id}")


# --- High-level orchestration over a Recruitment ------------------------


def _participant_discord_ids(recruitment) -> list[str]:
    ids = (
        recruitment.slots.filter(member__isnull=False)
        .values_list("member__discord_id", flat=True)
    )
    # De-dup while keeping it a plain list of non-empty strings.
    return [did for did in dict.fromkeys(ids) if did]


def provision_match_channels(recruitment) -> bool:
    """Create the private temp channels + invite for a filled recruitment.

    Idempotent: returns ``True`` and does nothing if already provisioned.
    On success the invite url, channel ids and cleanup time are saved on the
    recruitment. Returns ``False`` (without raising) if the bot is disabled.
    Raises ``DiscordError`` on API failure so callers/cron can retry.
    """
    if not settings.DISCORD_BOT_ENABLED:
        return False
    if recruitment.discord_provisioned_at:
        return True

    member_ids = _participant_discord_ids(recruitment)
    base_overwrites = [_everyone_deny_overwrite(), *_member_overwrites(member_ids)]
    label = f"{recruitment.mode}-{recruitment.pk}"

    created: list[str] = []
    try:
        parent_id = settings.DISCORD_PARENT_CATEGORY_ID or None
        category = create_channel(
            f"🎮 {label}", CHANNEL_CATEGORY, parent_id=parent_id, overwrites=base_overwrites
        )
        created.append(category["id"])
        text = create_channel(
            f"chat-{recruitment.pk}", CHANNEL_TEXT,
            parent_id=category["id"], overwrites=base_overwrites,
        )
        created.append(text["id"])
        voice = create_channel(
            f"VC-{recruitment.pk}", CHANNEL_VOICE,
            parent_id=category["id"], overwrites=base_overwrites,
        )
        created.append(voice["id"])
        # Invite lives a bit longer than the channels themselves.
        invite_url = create_invite(voice["id"], max_age=settings.DISCORD_CHANNEL_TTL)
    except DiscordError:
        # Roll back any half-created channels so a retry starts clean.
        for cid in reversed(created):
            try:
                delete_channel(cid)
            except DiscordError:
                logger.warning("一時チャンネルの巻き戻し削除に失敗: %s", cid)
        raise

    recruitment.discord_channel_ids = created
    recruitment.discord_auto_invite_url = invite_url
    recruitment.discord_provisioned_at = timezone.now()
    recruitment.discord_cleanup_at = recruitment.start_at + timezone.timedelta(
        seconds=settings.DISCORD_CHANNEL_TTL
    )
    recruitment.save(
        update_fields=[
            "discord_channel_ids",
            "discord_auto_invite_url",
            "discord_provisioned_at",
            "discord_cleanup_at",
        ]
    )
    return True


def teardown_match_channels(recruitment) -> None:
    """Delete the temporary channels created for a recruitment (F-DSC-05)."""
    for cid in recruitment.discord_channel_ids or []:
        delete_channel(cid)
    recruitment.discord_channel_ids = []
    recruitment.discord_auto_invite_url = ""
    recruitment.discord_cleanup_at = None
    recruitment.save(
        update_fields=[
            "discord_channel_ids",
            "discord_auto_invite_url",
            "discord_cleanup_at",
        ]
    )


def provision_safely(recruitment) -> None:
    """Best-effort provisioning for the request path; never raises.

    Used from the fill hook via ``transaction.on_commit``. Failures are logged
    and left for the periodic reconcile command to retry.
    """
    try:
        provision_match_channels(recruitment)
    except DiscordError as exc:
        logger.warning(
            "Discord チャンネル自動生成に失敗 (recruitment=%s): %s — 後続の定期同期で再試行します。",
            recruitment.pk,
            exc,
        )
