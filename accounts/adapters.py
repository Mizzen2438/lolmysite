"""django-allauth adapter wiring Discord OAuth to our custom user.

Responsibilities (ARCHITECTURE.md §5.1):
- Map the Discord account onto our passwordless ``User`` (discord_id is the key).
- Reject sign-ups from Discord accounts that are too new (F-UNIQ-07).
- Block login for Discord IDs with a suspension on record (F-UNIQ-04),
  even across account deletion / re-registration.
"""

from __future__ import annotations

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.shortcuts import render

from .models import SanctionRecord
from .utils import discord_id_to_created_at, is_discord_account_old_enough


def _discord_avatar_url(uid: str, extra: dict) -> str:
    avatar = extra.get("avatar")
    if avatar:
        return f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.png"
    return ""


class DiscordSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """Gatekeeping that runs after Discord auth, before login/signup."""
        uid = str(sociallogin.account.uid)

        # F-UNIQ-04: a suspension on this Discord ID blocks login outright,
        # surviving account deletion and re-registration.
        if SanctionRecord.objects.filter(
            discord_id=uid, type=SanctionRecord.Type.SUSPENSION
        ).exists():
            raise ImmediateHttpResponse(
                render(request, "accounts/blocked.html", {"reason": "suspended"}, status=403)
            )

        # F-UNIQ-07: brand-new Discord accounts cannot register. Existing
        # users are not re-checked so a later policy change won't lock them out.
        if not sociallogin.is_existing and not is_discord_account_old_enough(
            uid, settings.MIN_DISCORD_ACCOUNT_AGE_DAYS
        ):
            raise ImmediateHttpResponse(
                render(
                    request,
                    "accounts/blocked.html",
                    {
                        "reason": "too_young",
                        "min_age_days": settings.MIN_DISCORD_ACCOUNT_AGE_DAYS,
                    },
                    status=403,
                )
            )

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        uid = str(sociallogin.account.uid)
        extra = sociallogin.account.extra_data or {}
        user.discord_id = uid
        user.discord_name = (
            data.get("name") or extra.get("global_name") or extra.get("username") or ""
        )
        user.avatar_url = _discord_avatar_url(uid, extra)
        user.discord_created_at = discord_id_to_created_at(uid)
        return user
