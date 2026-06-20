from datetime import UTC, datetime
from time import time
from types import SimpleNamespace
from unittest import mock

from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import riot, services, views
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
        # Profile setup leads into Riot linking (M3).
        self.assertRedirects(resp, reverse("riot_link"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.profile_completed)
        self.assertEqual(self.user.lanes, ["TOP", "MID"])

    def test_completed_user_reaches_mypage(self):
        self.user.terms_agreed_at = timezone.now()
        self.user.profile_completed = True
        self.user.save(update_fields=["terms_agreed_at", "profile_completed"])
        resp = self.client.get(reverse("mypage"))
        self.assertEqual(resp.status_code, 200)


class RiotFormatTests(TestCase):
    def test_format_rank_with_division(self):
        self.assertEqual(riot.format_rank({"tier": "GOLD", "rank": "II"}), "ゴールド II")

    def test_format_rank_master_has_no_division(self):
        self.assertEqual(riot.format_rank({"tier": "MASTER", "rank": "I"}), "マスター")

    def test_format_rank_unknown_tier_is_empty(self):
        self.assertEqual(riot.format_rank({}), "")


@override_settings(RIOT_API_KEY="test-key")
class RiotClientTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_404_maps_to_not_found(self):
        resp = SimpleNamespace(status_code=404, headers={}, json=lambda: {})
        with mock.patch("accounts.riot.httpx.get", return_value=resp):
            with self.assertRaises(riot.RiotNotFound):
                riot.resolve_account("Nope", "JP1")

    def test_success_is_cached(self):
        resp = SimpleNamespace(
            status_code=200, headers={}, json=lambda: {"puuid": "PU", "gameName": "H", "tagLine": "JP1"}
        )
        with mock.patch("accounts.riot.httpx.get", return_value=resp) as get:
            riot.resolve_account("H", "JP1")
            riot.resolve_account("H", "JP1")  # served from cache
        self.assertEqual(get.call_count, 1)

    def test_missing_key_raises_config_error(self):
        with override_settings(RIOT_API_KEY=""):
            with self.assertRaises(riot.RiotConfigError):
                riot.resolve_account("H", "JP1")

    def test_fetch_ranks_uses_league_by_puuid(self):
        # League-V4 by-puuid is a single call (no Summoner-V4 / encrypted id).
        entries = [
            {"queueType": "RANKED_SOLO_5x5", "tier": "GOLD", "rank": "II"},
            {"queueType": "RANKED_FLEX_SR", "tier": "PLATINUM", "rank": "IV"},
        ]
        resp = SimpleNamespace(status_code=200, headers={}, json=lambda: entries)
        with mock.patch("accounts.riot.httpx.get", return_value=resp) as get:
            ranks = riot.fetch_ranks("PUUID-XYZ")
        self.assertEqual(get.call_count, 1)
        self.assertIn("by-puuid/PUUID-XYZ", get.call_args.args[0])
        self.assertEqual(ranks, {"solo": "ゴールド II", "flex": "プラチナ IV"})

    def test_third_party_code_is_not_cached(self):
        # Verification must always read live (player just set the code).
        resp = SimpleNamespace(status_code=200, headers={}, json=lambda: "ABCD1234")
        with mock.patch("accounts.riot.httpx.get", return_value=resp) as get:
            self.assertEqual(riot.fetch_third_party_code("PUUID-1"), "ABCD1234")
            riot.fetch_third_party_code("PUUID-1")
        self.assertEqual(get.call_count, 2)
        self.assertIn("third-party-code/by-puuid/PUUID-1", get.call_args.args[0])

    def test_third_party_code_missing_maps_to_not_found(self):
        resp = SimpleNamespace(status_code=404, headers={}, json=lambda: {})
        with mock.patch("accounts.riot.httpx.get", return_value=resp):
            with self.assertRaises(riot.RiotNotFound):
                riot.fetch_third_party_code("PUUID-1")


class RiotServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(discord_id="link-1")

    def _resolve(self):
        return mock.patch.object(
            services.riot, "resolve_account",
            return_value={"puuid": "PUUID-1", "gameName": "Hikari", "tagLine": "JP1"},
        )

    def _pending(self, code="CODE1234"):
        return {"puuid": "PUUID-1", "game_name": "Hikari", "tagline": "JP1", "code": code}

    # --- step 1: begin (issue code, nothing saved) ---

    def test_begin_returns_pending_and_saves_nothing(self):
        with self._resolve():
            pending = services.begin_riot_link(self.user, "Hikari", "JP1")
        self.assertEqual(pending["puuid"], "PUUID-1")
        self.assertEqual(pending["game_name"], "Hikari")
        self.assertEqual(len(pending["code"]), 8)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_riot_linked)  # not linked until verified

    def test_begin_duplicate_puuid_is_rejected(self):
        User.objects.create_user(discord_id="other", riot_puuid="PUUID-1")
        with self._resolve(), self.assertRaises(services.RiotLinkError):
            services.begin_riot_link(self.user, "Hikari", "JP1")

    def test_begin_not_found_raises(self):
        with mock.patch.object(services.riot, "resolve_account", side_effect=riot.RiotNotFound):
            with self.assertRaises(services.RiotLinkError):
                services.begin_riot_link(self.user, "Ghost", "JP1")

    # --- step 2: complete (verify ownership, then link) ---

    def test_complete_success_sets_puuid_and_rank(self):
        with mock.patch.object(services.riot, "fetch_third_party_code", return_value="CODE1234"), \
             mock.patch.object(services.riot, "fetch_ranks", return_value={"solo": "ゴールド II", "flex": ""}):
            services.complete_riot_link(self.user, self._pending("CODE1234"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.riot_puuid, "PUUID-1")
        self.assertEqual(self.user.riot_id, "Hikari#JP1")
        self.assertEqual(self.user.rank_solo, "ゴールド II")
        self.assertIsNotNone(self.user.rank_fetched_at)

    def test_complete_code_mismatch_does_not_link(self):
        with mock.patch.object(services.riot, "fetch_third_party_code", return_value="WRONG999"):
            with self.assertRaises(services.RiotLinkError):
                services.complete_riot_link(self.user, self._pending("CODE1234"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_riot_linked)

    def test_complete_code_not_set_yet_raises(self):
        with mock.patch.object(services.riot, "fetch_third_party_code", side_effect=riot.RiotNotFound):
            with self.assertRaises(services.RiotLinkError):
                services.complete_riot_link(self.user, self._pending("CODE1234"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_riot_linked)

    def test_complete_duplicate_puuid_is_rejected(self):
        User.objects.create_user(discord_id="other", riot_puuid="PUUID-1")
        with mock.patch.object(services.riot, "fetch_third_party_code", return_value="CODE1234"):
            with self.assertRaises(services.RiotLinkError):
                services.complete_riot_link(self.user, self._pending("CODE1234"))

    def test_refresh_respects_cooldown(self):
        self.user.riot_puuid = "PUUID-1"
        self.user.rank_fetched_at = timezone.now()
        self.user.save()
        self.assertFalse(services.can_refresh(self.user))
        with self.assertRaises(services.RiotLinkError):
            services.refresh_rank(self.user)

    def test_refresh_force_ignores_cooldown(self):
        self.user.riot_puuid = "PUUID-1"
        self.user.rank_fetched_at = timezone.now()
        self.user.save()
        with mock.patch.object(services.riot, "fetch_ranks", return_value={"solo": "プラチナ IV", "flex": ""}):
            services.refresh_rank(self.user, force=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.rank_solo, "プラチナ IV")


class RiotViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(discord_id="view-1")
        self.user.terms_agreed_at = timezone.now()
        self.user.profile_completed = True
        self.user.save()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def _pending(self, code="CODE1234"):
        return {
            "puuid": "PUUID-1", "game_name": "Hikari", "tagline": "JP1",
            "code": code, "ts": timezone.now().timestamp(),
        }

    def _set_pending(self, pending=None):
        session = self.client.session
        session[views.RIOT_LINK_SESSION_KEY] = pending or self._pending()
        session.save()

    def test_riot_link_post_redirects_to_verify(self):
        pending = {"puuid": "PUUID-1", "game_name": "Hikari", "tagline": "JP1", "code": "CODE1234"}
        with mock.patch("accounts.views.begin_riot_link", return_value=pending) as begin:
            resp = self.client.post(
                reverse("riot_link"), {"game_name": "Hikari", "tagline": "JP1"}
            )
        begin.assert_called_once()
        self.assertRedirects(resp, reverse("riot_verify"))
        self.assertIn(views.RIOT_LINK_SESSION_KEY, self.client.session)

    def test_riot_link_post_error_stays_on_page(self):
        with mock.patch(
            "accounts.views.begin_riot_link",
            side_effect=services.RiotLinkError("見つかりません"),
        ):
            resp = self.client.post(
                reverse("riot_link"), {"game_name": "Ghost", "tagline": "JP1"}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(views.RIOT_LINK_SESSION_KEY, self.client.session)

    def test_verify_without_pending_redirects_to_link(self):
        resp = self.client.get(reverse("riot_verify"))
        self.assertRedirects(resp, reverse("riot_link"))

    def test_verify_get_shows_code(self):
        self._set_pending()
        resp = self.client.get(reverse("riot_verify"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CODE1234")

    def test_verify_post_success_redirects_to_mypage(self):
        self._set_pending()
        with mock.patch("accounts.views.complete_riot_link") as complete:
            resp = self.client.post(reverse("riot_verify"))
        complete.assert_called_once()
        self.assertRedirects(resp, reverse("mypage"))
        self.assertNotIn(views.RIOT_LINK_SESSION_KEY, self.client.session)

    def test_verify_post_error_keeps_pending(self):
        self._set_pending()
        with mock.patch(
            "accounts.views.complete_riot_link",
            side_effect=services.RiotLinkError("まだ確認できません"),
        ):
            resp = self.client.post(reverse("riot_verify"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(views.RIOT_LINK_SESSION_KEY, self.client.session)

    def test_refresh_requires_post(self):
        resp = self.client.get(reverse("riot_refresh"))
        self.assertEqual(resp.status_code, 405)


class RefreshRanksCommandTests(TestCase):
    def test_refreshes_active_linked_users(self):
        active = User.objects.create_user(discord_id="active", riot_puuid="P-A")
        active.last_login = timezone.now()
        active.save()
        # Inactive (no recent login) and unlinked users are skipped.
        User.objects.create_user(discord_id="unlinked")
        with mock.patch.object(services.riot, "fetch_ranks", return_value={"solo": "ゴールド I", "flex": ""}):
            call_command("refresh_ranks", "--sleep", "0")
        active.refresh_from_db()
        self.assertEqual(active.rank_solo, "ゴールド I")


class DevLoginTests(TestCase):
    @override_settings(DEV_LOGIN_ENABLED=False)
    def test_dev_login_404_when_disabled(self):
        self.assertEqual(self.client.get(reverse("dev_login")).status_code, 404)

    @override_settings(DEV_LOGIN_ENABLED=True)
    def test_dev_login_logs_in_when_enabled(self):
        user = User.objects.create_user(discord_id="dev-1", discord_name="demo")
        user.terms_agreed_at = timezone.now()
        user.profile_completed = True
        user.save()
        self.assertEqual(self.client.get(reverse("dev_login")).status_code, 200)
        resp = self.client.post(reverse("dev_login"), {"user_id": user.pk})
        self.assertRedirects(resp, reverse("post_login"), target_status_code=302)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))


class SeedDemoCommandTests(TestCase):
    def test_seed_creates_data_and_is_idempotent(self):
        call_command("seed_demo")
        from applications.models import Application
        from recruitments.models import Recruitment

        self.assertEqual(User.objects.filter(discord_id__startswith="9000").count(), 4)
        self.assertEqual(Recruitment.objects.count(), 3)
        self.assertEqual(Application.objects.count(), 1)
        call_command("seed_demo")  # second run must not duplicate
        self.assertEqual(Recruitment.objects.count(), 3)


class RiotTxtTests(TestCase):
    @override_settings(RIOT_VERIFICATION_CODE="abc-123-verify")
    def test_riot_txt_returns_exact_code(self):
        resp = self.client.get("/riot.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/plain")
        self.assertEqual(resp.content.decode(), "abc-123-verify")
