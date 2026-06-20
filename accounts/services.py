"""Riot account linking and rank refresh (M3, ARCHITECTURE.md §5.2)."""

from __future__ import annotations

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from . import riot
from .models import User


class RiotLinkError(Exception):
    """User-facing error during Riot linking / refresh."""


def link_riot_account(user: User, game_name: str, tagline: str) -> User:
    """Manual (unverified) linking: resolve a Riot ID and store rank.

    Used as a fallback when RSO is not enabled. Ownership is NOT proven here —
    only PUUID uniqueness (F-UNIQ-03) is enforced. Raises RiotLinkError with a
    Japanese message on any failure.
    """
    game_name = game_name.strip()
    tagline = tagline.strip().lstrip("#")

    try:
        account = riot.resolve_account(game_name, tagline)
    except riot.RiotNotFound as exc:
        raise RiotLinkError("その Riot ID は見つかりませんでした。入力を確認してください。") from exc
    except riot.RiotConfigError as exc:
        raise RiotLinkError("現在 Riot 連携を利用できません。時間をおいてお試しください。") from exc
    except riot.RiotRateLimited as exc:
        raise RiotLinkError("混み合っています。しばらくしてからお試しください。") from exc
    except riot.RiotError as exc:
        raise RiotLinkError("Riot との通信でエラーが発生しました。") from exc

    return _finalize_link(
        user,
        account["puuid"],
        account.get("gameName", game_name),
        account.get("tagLine", tagline),
    )


def complete_rso_link(user: User, puuid: str) -> User:
    """Link an RSO-verified account (ownership already proven by sign-in).

    ``puuid`` comes from the verified id_token. We best-effort look up the
    display Riot ID, then finalise the link and fetch rank.
    """
    game_name = ""
    tagline = ""
    try:
        account = riot.resolve_account_by_puuid(puuid)
        game_name = account.get("gameName", "")
        tagline = account.get("tagLine", "")
    except riot.RiotError:
        # The display name is non-essential; ownership is already proven.
        pass
    return _finalize_link(user, puuid, game_name, tagline)


def _finalize_link(user: User, puuid: str, game_name: str, tagline: str) -> User:
    # F-UNIQ-03: a PUUID may belong to only one user.
    if User.objects.filter(riot_puuid=puuid).exclude(pk=user.pk).exists():
        raise RiotLinkError("この Riot アカウントは既に別のユーザーに登録されています。")

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
