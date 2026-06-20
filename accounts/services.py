"""Riot account linking and rank refresh (M3, ARCHITECTURE.md §5.2).

Linking is two-step to prove account ownership (F-UNIQ-03): we resolve the
Riot ID to a PUUID and issue a one-time verification code, the player enters
that code in their LoL client (設定 → 検証), and only after we read it back via
the third-party-code endpoint do we finalise the link. This stops anyone from
claiming a Riot ID they do not actually control.
"""

from __future__ import annotations

import secrets

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from . import riot
from .models import User

# Unambiguous alphabet (no O/0/I/1/etc.) for the verification code the user has
# to copy into the LoL client by hand.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class RiotLinkError(Exception):
    """User-facing error during Riot linking / refresh."""


def generate_verification_code(length: int = 8) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def begin_riot_link(user: User, game_name: str, tagline: str) -> dict:
    """Step 1: resolve the Riot ID and issue a verification code.

    Nothing is persisted. The caller stores the returned pending data (e.g. in
    the session) and shows the code to the user; the link is only made in
    :func:`complete_riot_link` once ownership is proven.
    """
    game_name = game_name.strip()
    tagline = tagline.strip().lstrip("#")

    account = _resolve_or_error(game_name, tagline)
    puuid = account["puuid"]
    _ensure_puuid_available(puuid, user)

    return {
        "puuid": puuid,
        "game_name": account.get("gameName", game_name),
        "tagline": account.get("tagLine", tagline),
        "code": generate_verification_code(),
    }


def complete_riot_link(user: User, pending: dict) -> User:
    """Step 2: confirm the code is set in the LoL client, then link + fetch rank.

    ``pending`` is the dict returned by :func:`begin_riot_link`. Raises
    RiotLinkError if the code is not set yet or does not match.
    """
    puuid = pending["puuid"]

    try:
        actual_code = riot.fetch_third_party_code(puuid)
    except riot.RiotNotFound as exc:
        raise RiotLinkError(
            "まだ確認できません。LoL クライアントの「設定 → 検証」にコードを入力し、"
            "数十秒おいてからもう一度お試しください。"
        ) from exc
    except riot.RiotConfigError as exc:
        raise RiotLinkError("現在 Riot 連携を利用できません。時間をおいてお試しください。") from exc
    except riot.RiotRateLimited as exc:
        raise RiotLinkError("混み合っています。しばらくしてからお試しください。") from exc
    except riot.RiotError as exc:
        raise RiotLinkError("Riot との通信でエラーが発生しました。") from exc

    if actual_code != pending["code"]:
        raise RiotLinkError(
            "コードが一致しません。LoL クライアントの「設定 → 検証」に表示のコードを"
            "正確に入力し、数十秒おいてからもう一度お試しください。"
        )

    return _finalize_link(user, puuid, pending["game_name"], pending["tagline"])


def _resolve_or_error(game_name: str, tagline: str) -> dict:
    try:
        return riot.resolve_account(game_name, tagline)
    except riot.RiotNotFound as exc:
        raise RiotLinkError("その Riot ID は見つかりませんでした。入力を確認してください。") from exc
    except riot.RiotConfigError as exc:
        raise RiotLinkError("現在 Riot 連携を利用できません。時間をおいてお試しください。") from exc
    except riot.RiotRateLimited as exc:
        raise RiotLinkError("混み合っています。しばらくしてからお試しください。") from exc
    except riot.RiotError as exc:
        raise RiotLinkError("Riot との通信でエラーが発生しました。") from exc


def _ensure_puuid_available(puuid: str, user: User) -> None:
    # F-UNIQ-03: a PUUID may belong to only one user.
    if User.objects.filter(riot_puuid=puuid).exclude(pk=user.pk).exists():
        raise RiotLinkError("この Riot アカウントは既に別のユーザーに登録されています。")


def _finalize_link(user: User, puuid: str, game_name: str, tagline: str) -> User:
    _ensure_puuid_available(puuid, user)
    user.riot_puuid = puuid
    user.riot_game_name = game_name
    user.riot_tagline = tagline
    _apply_ranks(user)
    try:
        user.save(
            update_fields=[
                "riot_puuid",
                "riot_game_name",
                "riot_tagline",
                "rank_solo",
                "rank_flex",
                "rank_fetched_at",
            ]
        )
    except IntegrityError as exc:
        # Lost a race: another user linked this PUUID between the check and save.
        raise RiotLinkError("この Riot アカウントは既に別のユーザーに登録されています。") from exc
    return user


def refresh_rank(user: User, *, force: bool = False) -> User:
    """Re-fetch rank for a linked user, honouring the refresh cooldown."""
    if not user.riot_puuid:
        raise RiotLinkError("先に Riot ID を連携してください。")
    if not force and not can_refresh(user):
        raise RiotLinkError("ランクの更新は時間をおいて行ってください。")

    _apply_ranks(user)
    user.save(update_fields=["rank_solo", "rank_flex", "rank_fetched_at"])
    return user


def can_refresh(user: User) -> bool:
    """Whether the cooldown since the last manual refresh has elapsed."""
    if user.rank_fetched_at is None:
        return True
    elapsed = (timezone.now() - user.rank_fetched_at).total_seconds()
    return elapsed >= settings.RIOT_REFRESH_COOLDOWN


def _apply_ranks(user: User) -> None:
    ranks = riot.fetch_ranks(user.riot_puuid)
    user.rank_solo = ranks["solo"]
    user.rank_flex = ranks["flex"]
    user.rank_fetched_at = timezone.now()
