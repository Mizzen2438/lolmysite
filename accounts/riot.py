"""Riot Games API client (M3, ARCHITECTURE.md §5.2).

Wraps the three endpoints we need:
- Account-V1: Riot ID (gameName#tagLine) -> PUUID, also used for existence check
- Summoner-V4: PUUID -> encrypted summoner id
- League-V4: summoner id -> ranked entries

Successful responses are cached (N-13) so repeated lookups and API outages do
not hit Riot every time. Errors are surfaced as typed exceptions for the
service layer to translate into user-facing messages.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx
from django.conf import settings
from django.core.cache import cache


class RiotError(Exception):
    """Generic Riot API failure."""


class RiotNotFound(RiotError):
    """The requested Riot ID / summoner does not exist."""


class RiotRateLimited(RiotError):
    def __init__(self, retry_after: int = 1):
        self.retry_after = retry_after
        super().__init__(f"Rate limited; retry after {retry_after}s")


class RiotConfigError(RiotError):
    """API key missing, invalid or expired."""


# Riot tier (English) -> display name (Japanese), matching games fixture order.
TIER_JA = {
    "IRON": "アイアン",
    "BRONZE": "ブロンズ",
    "SILVER": "シルバー",
    "GOLD": "ゴールド",
    "PLATINUM": "プラチナ",
    "EMERALD": "エメラルド",
    "DIAMOND": "ダイヤモンド",
    "MASTER": "マスター",
    "GRANDMASTER": "グランドマスター",
    "CHALLENGER": "チャレンジャー",
}
# Apex tiers have no division.
_NO_DIVISION = {"MASTER", "GRANDMASTER", "CHALLENGER"}


def format_rank(entry: dict) -> str:
    """Turn a League-V4 entry into e.g. 'ゴールド II' or 'マスター'."""
    tier = (entry.get("tier") or "").upper()
    tier_ja = TIER_JA.get(tier)
    if not tier_ja:
        return ""
    if tier in _NO_DIVISION:
        return tier_ja
    division = entry.get("rank", "")
    return f"{tier_ja} {division}".strip()


def _request(url: str, *, cache_key: str) -> dict | list:
    if not settings.RIOT_API_KEY:
        raise RiotConfigError("RIOT_API_KEY が設定されていません。")

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = httpx.get(
            url,
            headers={"X-Riot-Token": settings.RIOT_API_KEY},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise RiotError(f"Riot API への接続に失敗しました: {exc}") from exc

    if resp.status_code == 200:
        data = resp.json()
        cache.set(cache_key, data, settings.RIOT_CACHE_TTL)
        return data
    if resp.status_code == 404:
        raise RiotNotFound()
    if resp.status_code == 429:
        raise RiotRateLimited(int(resp.headers.get("Retry-After", "1")))
    if resp.status_code in (401, 403):
        raise RiotConfigError("Riot API キーが無効または期限切れです。")
    raise RiotError(f"Riot API エラー (status {resp.status_code})")


def resolve_account(game_name: str, tagline: str) -> dict:
    """Account-V1 lookup. Returns dict with puuid/gameName/tagLine."""
    key = f"riot:account:{game_name.lower()}#{tagline.lower()}"
    url = (
        f"https://{settings.RIOT_REGIONAL}.api.riotgames.com"
        f"/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tagline)}"
    )
    return _request(url, cache_key=key)


def fetch_ranks(puuid: str) -> dict:
    """Return {'solo': '<rank>', 'flex': '<rank>'} for the given PUUID.

    Missing queues come back as empty strings (treated as アンランク).
    """
    summoner = _request(
        f"https://{settings.RIOT_PLATFORM}.api.riotgames.com"
        f"/lol/summoner/v4/summoners/by-puuid/{puuid}",
        cache_key=f"riot:summoner:{puuid}",
    )
    summoner_id = summoner["id"]
    entries = _request(
        f"https://{settings.RIOT_PLATFORM}.api.riotgames.com"
        f"/lol/league/v4/entries/by-summoner/{summoner_id}",
        cache_key=f"riot:league:{summoner_id}",
    )
    ranks = {"solo": "", "flex": ""}
    for entry in entries:
        if entry.get("queueType") == "RANKED_SOLO_5x5":
            ranks["solo"] = format_rank(entry)
        elif entry.get("queueType") == "RANKED_FLEX_SR":
            ranks["flex"] = format_rank(entry)
    return ranks
