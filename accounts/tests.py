from datetime import UTC, datetime
from time import time
from types import SimpleNamespace

from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .adapters import DiscordSocialAccountAdapter
from .models import SanctionRecord
from .utils import discord_id_to_created_at, is_discord_account_old_enough

User = get_user_model()


def _recent_discord_id() -> str:
    """A snowflake for an account created right now (fails the age gate)."""
    ms = int(time() * 1000)
    return str((ms - 1420070400000) << 22)


OLD_DISCORD_ID = "175928847299117063"  # created 2016


class SnowflakeUtilTests(TestCase):
    def test_known_snowflake_decodes_to_creation_time(self):
        # Discord documentation's reference snowflake.
        created = discord_id_to_created_at(175928847299117063)
        self.assertEqual(created.year, 2016)
        self.assertEqual(created.month, 4)

    def test_account_age_gate(self):
        now = datetime(2026, 6, 15, tzinfo=UTC)
        # An account created in 2016 is clearly older than 90 days.
        self.assertTrue(
            is_discord_account_old_enough("175928847299117063", 90, now=now)
        )


class UserModelTests(TestCase):
    def test_create_user_has_no_usable_password(self):
        user = User.objects.create_user(discord_id="123", discord_name="tester")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(str(user), "tester")
        self.assertFalse(user.is_riot_linked)

    def test_create_superuser_can_access_admin(self):
        admin = User.objects.create_superuser(discord_id="999", password="pw-secret-123")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.has_usable_password())

    def test_discord_id_is_unique(self):
        User.objects.create_user(discord_id="555")
        with self.assertRaises(IntegrityError):
            User.objects.create_user(discord_id="555")

    def test_riot_id_property(self):
        user = User.objects.create_user(
            discord_id="222", riot_game_name="Hikari", riot_tagline="JP1"
        )
        self.assertEqual(user.riot_id, "Hikari#JP1")


class AdapterTests(TestCase):
    def setUp(self):
        self.adapter = DiscordSocialAccountAdapter()
        self.request = RequestFactory().get("/accounts/discord/login/callback/")

    def _sociallogin(self, uid, *, is_existing=False, extra=None):
        return SimpleNamespace(
            account=SimpleNamespace(uid=uid, extra_data=extra or {}),
            is_existing=is_existing,
            user=User(),
        )

    def test_old_account_passes(self):
        # No exception raised for an account well past the age threshold.
        self.adapter.pre_social_login(self.request, self._sociallogin(OLD_DISCORD_ID))

    def test_new_account_is_rejected(self):
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(
                self.request, self._sociallogin(_recent_discord_id())
            )

    def test_existing_user_skips_age_check(self):
        # Existing users are not re-checked even if their account is new.
        self.adapter.pre_social_login(
            self.request, self._sociallogin(_recent_discord_id(), is_existing=True)
        )

    def test_suspended_discord_id_is_blocked(self):
        SanctionRecord.objects.create(
            discord_id=OLD_DISCORD_ID,
            type=SanctionRecord.Type.SUSPENSION,
            reason="暴言",
        )
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(self.request, self._sociallogin(OLD_DISCORD_ID))

    def test_populate_user_sets_discord_fields(self):
        sl = self._sociallogin(
            OLD_DISCORD_ID, extra={"global_name": "Hikari", "avatar": "abc123"}
        )
        user = self.adapter.populate_user(self.request, sl, {"name": "Hikari"})
        self.assertEqual(user.discord_id, OLD_DISCORD_ID)
        self.assertEqual(user.discord_name, "Hikari")
        self.assertIn(OLD_DISCORD_ID, user.avatar_url)
        self.assertEqual(user.discord_created_at.year, 2016)


class OnboardingFlowTests(TestCase):
    BACKEND = "django.contrib.auth.backends.ModelBackend"

    def setUp(self):
        self.user = User.objects.create_user(discord_id="123456789", discord_name="newbie")
        self.client.force_login(self.user, backend=self.BACKEND)

    def test_unagreed_user_is_redirected_to_terms(self):
        resp = self.client.get(reverse("mypage"))
        self.assertRedirects(resp, reverse("terms"))

    def test_agreeing_terms_advances_to_profile_setup(self):
        resp = self.client.post(reverse("terms"), {"agree": "1"})
        self.assertRedirects(resp, reverse("profile_setup"))
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.terms_agreed_at)

    def test_terms_without_checkbox_does_not_advance(self):
        resp = self.client.post(reverse("terms"), {})
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.terms_agreed_at)

    def test_profile_setup_completes_onboarding(self):
        self.user.terms_agreed_at = timezone.now()
        self.user.save(update_fields=["terms_agreed_at"])
        resp = self.client.post(
            reverse("profile_setup"),
            {"lanes": ["TOP", "MID"], "play_hours": "夜", "vc_style": "talk", "bio": "よろしく"},
        )
        self.assertRedirects(resp, reverse("mypage"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.profile_completed)
        self.assertEqual(self.user.lanes, ["TOP", "MID"])

    def test_completed_user_reaches_mypage(self):
        self.user.terms_agreed_at = timezone.now()
        self.user.profile_completed = True
        self.user.save(update_fields=["terms_agreed_at", "profile_completed"])
        resp = self.client.get(reverse("mypage"))
        self.assertEqual(resp.status_code, 200)
