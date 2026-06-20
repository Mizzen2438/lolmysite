from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from games.models import Game
from moderation.models import Block
from notifications.models import Notification
from recruitments.models import Recruitment, RecruitmentSlot

from . import services
from .models import Application

User = get_user_model()
BACKEND = "django.contrib.auth.backends.ModelBackend"


def make_game():
    return Game.objects.create(
        name="LoL", slug="league-of-legends",
        modes=["ランク(フレックス)"], lanes=["TOP", "JG", "MID", "ADC", "SUP", "FILL"],
        rank_tiers=["アイアン", "ブロンズ", "シルバー", "ゴールド", "プラチナ"],
    )


def make_user(discord_id, *, linked=True, rank="ゴールド II"):
    u = User.objects.create_user(discord_id=discord_id, discord_name=discord_id)
    u.terms_agreed_at = timezone.now()
    u.profile_completed = True
    if linked:
        u.riot_puuid = f"PU-{discord_id}"
        u.rank_solo = rank
    u.save()
    return u


def make_recruitment(owner, game, *, open_lanes=("MID",), **kw):
    rec = Recruitment.objects.create(
        game=game, owner=owner, mode="ランク(フレックス)",
        start_at=timezone.now() + timedelta(hours=2), **kw,
    )
    RecruitmentSlot.objects.create(recruitment=rec, lane="TOP", member=owner)
    for lane in open_lanes:
        RecruitmentSlot.objects.create(recruitment=rec, lane=lane)
    return rec


class EligibilityTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = make_user("owner")
        self.rec = make_recruitment(self.owner, self.game)

    def test_owner_cannot_apply(self):
        with self.assertRaises(services.ApplicationError):
            services.check_can_apply(self.owner, self.rec)

    def test_unlinked_cannot_apply(self):
        applicant = make_user("nolink", linked=False)
        with self.assertRaises(services.ApplicationError):
            services.check_can_apply(applicant, self.rec)

    def test_blocked_cannot_apply(self):
        applicant = make_user("blocked")
        Block.objects.create(user=self.owner, blocked_user=applicant)
        with self.assertRaises(services.ApplicationError):
            services.check_can_apply(applicant, self.rec)

    def test_closed_recruitment_rejects(self):
        applicant = make_user("late")
        self.rec.status = Recruitment.Status.CLOSED
        self.rec.save()
        with self.assertRaises(services.ApplicationError):
            services.check_can_apply(applicant, self.rec)

    def test_hidden_recruitment_rejects(self):
        applicant = make_user("hid")
        self.rec.is_hidden = True
        self.rec.save()
        with self.assertRaises(services.ApplicationError):
            services.check_can_apply(applicant, self.rec)

    def test_duplicate_active_application_rejected(self):
        applicant = make_user("dup")
        services.apply(applicant, self.rec, "MID")
        with self.assertRaises(services.ApplicationError):
            services.check_can_apply(applicant, self.rec)


class ApplyApproveFlowTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = make_user("owner")
        self.applicant = make_user("applicant")

    def test_apply_creates_pending_and_notifies_owner(self):
        rec = make_recruitment(self.owner, self.game)
        app = services.apply(self.applicant, rec, "MID", "よろしく")
        self.assertEqual(app.status, Application.Status.PENDING)
        self.assertTrue(
            Notification.objects.filter(
                user=self.owner, type=Notification.Type.APPLICATION_RECEIVED
            ).exists()
        )

    def test_approve_assigns_slot_and_notifies(self):
        rec = make_recruitment(self.owner, self.game, open_lanes=("MID", "ADC"))
        app = services.apply(self.applicant, rec, "MID")
        services.approve(app)
        app.refresh_from_db()
        self.assertEqual(app.status, Application.Status.APPROVED)
        self.assertTrue(rec.slots.filter(lane="MID", member=self.applicant).exists())
        self.assertTrue(
            Notification.objects.filter(
                user=self.applicant, type=Notification.Type.APPLICATION_APPROVED
            ).exists()
        )
        rec.refresh_from_db()
        self.assertEqual(rec.status, Recruitment.Status.OPEN)  # ADC still open

    def test_filling_last_slot_marks_filled_and_notifies_all(self):
        rec = make_recruitment(self.owner, self.game, open_lanes=("MID",))
        app = services.apply(self.applicant, rec, "MID")
        services.approve(app)
        rec.refresh_from_db()
        self.assertEqual(rec.status, Recruitment.Status.FILLED)
        # Both owner and applicant get the meetup notice (F-DSC-03).
        self.assertEqual(
            Notification.objects.filter(type=Notification.Type.RECRUITMENT_FILLED).count(), 2
        )

    def test_reject_notifies_applicant(self):
        rec = make_recruitment(self.owner, self.game)
        app = services.apply(self.applicant, rec, "MID")
        services.reject(app)
        app.refresh_from_db()
        self.assertEqual(app.status, Application.Status.REJECTED)
        self.assertTrue(
            Notification.objects.filter(
                user=self.applicant, type=Notification.Type.APPLICATION_REJECTED
            ).exists()
        )

    def test_withdraw(self):
        rec = make_recruitment(self.owner, self.game)
        app = services.apply(self.applicant, rec, "MID")
        services.withdraw(app)
        app.refresh_from_db()
        self.assertEqual(app.status, Application.Status.WITHDRAWN)

    def test_decline_reopens_filled_recruitment(self):
        rec = make_recruitment(self.owner, self.game, open_lanes=("MID",))
        app = services.apply(self.applicant, rec, "MID")
        services.approve(app)
        rec.refresh_from_db()
        self.assertEqual(rec.status, Recruitment.Status.FILLED)
        services.decline(app)
        app.refresh_from_db()
        rec.refresh_from_db()
        self.assertEqual(app.status, Application.Status.DECLINED)
        self.assertEqual(rec.status, Recruitment.Status.OPEN)
        self.assertFalse(rec.slots.filter(member=self.applicant).exists())

    def test_decline_after_start_expires_recruitment(self):
        rec = make_recruitment(self.owner, self.game, open_lanes=("MID",))
        app = services.apply(self.applicant, rec, "MID")
        services.approve(app)
        # Start time slips into the past while the match is filled.
        Recruitment.objects.filter(pk=rec.pk).update(
            start_at=timezone.now() - timedelta(minutes=1)
        )
        services.decline(app)
        rec.refresh_from_db()
        self.assertEqual(rec.status, Recruitment.Status.EXPIRED)

    def test_reapply_after_withdraw(self):
        rec = make_recruitment(self.owner, self.game)
        app = services.apply(self.applicant, rec, "MID")
        services.withdraw(app)
        again = services.apply(self.applicant, rec, "MID")
        self.assertEqual(again.pk, app.pk)
        self.assertEqual(again.status, Application.Status.PENDING)

    def test_rank_band_warning(self):
        rec = make_recruitment(self.owner, self.game, rank_min_idx=0, rank_max_idx=1)  # アイアン〜ブロンズ
        # applicant is ゴールド -> out of band
        self.assertIsNotNone(services.rank_band_warning(self.applicant, rec))
        rec2 = make_recruitment(self.owner, self.game, rank_min_idx=3, rank_max_idx=4)  # ゴールド〜プラチナ
        self.assertIsNone(services.rank_band_warning(self.applicant, rec2))


class ApplicationViewTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = make_user("owner")
        self.applicant = make_user("applicant")
        self.rec = make_recruitment(self.owner, self.game, open_lanes=("MID", "ADC"))

    def test_full_flow_via_views(self):
        # Applicant applies.
        self.client.force_login(self.applicant, backend=BACKEND)
        self.client.post(
            reverse("application_apply", args=[self.rec.pk]),
            {"desired_lane": "MID", "comment": "参加します"},
        )
        app = Application.objects.get(recruitment=self.rec, applicant=self.applicant)
        self.assertEqual(app.status, Application.Status.PENDING)

        # Owner approves.
        self.client.force_login(self.owner, backend=BACKEND)
        self.client.post(reverse("application_approve", args=[app.pk]))
        app.refresh_from_db()
        self.assertEqual(app.status, Application.Status.APPROVED)

    def test_non_owner_cannot_approve(self):
        app = services.apply(self.applicant, self.rec, "MID")
        stranger = make_user("stranger")
        self.client.force_login(stranger, backend=BACKEND)
        self.client.post(reverse("application_approve", args=[app.pk]))
        app.refresh_from_db()
        self.assertEqual(app.status, Application.Status.PENDING)

    def test_detail_shows_apply_form_for_eligible(self):
        self.client.force_login(self.applicant, backend=BACKEND)
        resp = self.client.get(reverse("recruitment_detail", args=[self.rec.pk]))
        self.assertContains(resp, "この募集に応募する")


# --- Discord temp-channel provisioning (F-DSC-05) -----------------------

from unittest import mock  # noqa: E402

from django.test import override_settings  # noqa: E402

from applications import discord  # noqa: E402

DISCORD_ON = dict(
    DISCORD_BOT_ENABLED=True,
    DISCORD_BOT_TOKEN="bot-token",
    DISCORD_GUILD_ID="9999",
    DISCORD_PARENT_CATEGORY_ID="",
    DISCORD_CHANNEL_TTL=3600,
)


@override_settings(**DISCORD_ON)
class DiscordProvisioningTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = make_user("owner")  # discord_id="owner"
        self.applicant = make_user("applicant")
        self.rec = make_recruitment(self.owner, self.game, open_lanes=("MID",))

    def _fill(self):
        app = services.apply(self.applicant, self.rec, "MID")
        # Approve outside the on_commit-capturing block in callers as needed.
        return app

    def _fake_request(self):
        """Return a _request stand-in that mints sequential channel ids."""
        state = {"n": 0}

        def fake(method, path, *, json=None):
            if method == "POST" and path.endswith("/invites"):
                return {"code": "abc123"}
            if method == "POST" and "/channels" in path:
                state["n"] += 1
                return {"id": f"chan{state['n']}"}
            if method == "DELETE":
                return None
            return {}

        return fake

    def test_provision_creates_private_channels_and_saves(self):
        services.approve(self._fill())
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.status, Recruitment.Status.FILLED)

        calls = []

        def recording(method, path, *, json=None):
            calls.append((method, path, json))
            if path.endswith("/invites"):
                return {"code": "inv9"}
            if "/channels" in path:
                return {"id": f"c{len([c for c in calls if '/channels' in c[1]])}"}
            return None

        with mock.patch.object(discord, "_request", side_effect=recording):
            ok = discord.provision_match_channels(self.rec)

        self.assertTrue(ok)
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.discord_auto_invite_url, "https://discord.gg/inv9")
        self.assertEqual(len(self.rec.discord_channel_ids), 3)  # category + text + voice
        self.assertIsNotNone(self.rec.discord_provisioned_at)
        self.assertIsNotNone(self.rec.discord_cleanup_at)

        # First created channel is the category and carries the @everyone deny
        # plus an allow overwrite for each participant's discord_id.
        first_channel = next(c for c in calls if "/channels" in c[1])
        overwrites = first_channel[2]["permission_overwrites"]
        ids = {o["id"] for o in overwrites}
        self.assertIn("9999", ids)  # @everyone (= guild id) deny
        self.assertIn("owner", ids)
        self.assertIn("applicant", ids)

    def test_provision_is_idempotent(self):
        self.rec.discord_provisioned_at = timezone.now()
        self.rec.save(update_fields=["discord_provisioned_at"])
        with mock.patch.object(discord, "_request") as m:
            self.assertTrue(discord.provision_match_channels(self.rec))
        m.assert_not_called()

    @override_settings(DISCORD_BOT_ENABLED=False)
    def test_provision_noop_when_disabled(self):
        with mock.patch.object(discord, "_request") as m:
            self.assertFalse(discord.provision_match_channels(self.rec))
        m.assert_not_called()

    def test_provision_rolls_back_on_failure(self):
        deleted = []

        def flaky(method, path, *, json=None):
            if method == "DELETE":
                deleted.append(path)
                return None
            if path.endswith("/invites"):
                raise discord.DiscordError("boom")  # fail at the last step
            return {"id": f"chan{len(deleted) + len(path)}"}

        with mock.patch.object(discord, "_request", side_effect=flaky):
            with self.assertRaises(discord.DiscordError):
                discord.provision_match_channels(self.rec)

        self.rec.refresh_from_db()
        self.assertEqual(self.rec.discord_channel_ids, [])
        self.assertIsNone(self.rec.discord_provisioned_at)
        # The 3 created channels were each deleted during rollback.
        self.assertEqual(len(deleted), 3)

    def test_fill_schedules_provisioning_on_commit(self):
        app = services.apply(self.applicant, self.rec, "MID")
        with mock.patch.object(discord, "provision_match_channels") as prov:
            with self.captureOnCommitCallbacks(execute=True):
                services.approve(app)
        prov.assert_called_once()

    def test_teardown_deletes_channels(self):
        self.rec.discord_channel_ids = ["a", "b", "c"]
        self.rec.discord_auto_invite_url = "https://discord.gg/x"
        self.rec.discord_cleanup_at = timezone.now()
        self.rec.save()
        with mock.patch.object(discord, "_request") as m:
            discord.teardown_match_channels(self.rec)
        self.assertEqual(m.call_count, 3)
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.discord_channel_ids, [])
        self.assertEqual(self.rec.discord_auto_invite_url, "")


@override_settings(**DISCORD_ON)
class DiscordSyncCommandTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = make_user("owner")

    def test_command_provisions_pending_and_cleans_expired(self):
        from django.core.management import call_command

        pending = make_recruitment(self.owner, self.game, status=Recruitment.Status.FILLED)
        expired = make_recruitment(
            self.owner, self.game,
            status=Recruitment.Status.FILLED,
            discord_provisioned_at=timezone.now() - timedelta(hours=8),
            discord_channel_ids=["x", "y"],
            discord_cleanup_at=timezone.now() - timedelta(minutes=1),
        )

        with mock.patch.object(discord, "provision_match_channels") as prov, \
             mock.patch.object(discord, "teardown_match_channels") as tear:
            call_command("sync_discord_channels")

        prov.assert_called_once()
        self.assertEqual(prov.call_args.args[0].pk, pending.pk)
        tear.assert_called_once()
        self.assertEqual(tear.call_args.args[0].pk, expired.pk)


class DiscordClientTests(TestCase):
    @override_settings(**DISCORD_ON)
    def test_request_sends_bot_auth_and_parses_json(self):
        fake_resp = mock.Mock(status_code=200)
        fake_resp.json.return_value = {"id": "123"}
        with mock.patch("applications.discord.httpx.request", return_value=fake_resp) as req:
            out = discord._request("POST", "/guilds/9999/channels", json={"name": "x"})
        self.assertEqual(out, {"id": "123"})
        _, kwargs = req.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bot bot-token")

    @override_settings(DISCORD_BOT_ENABLED=False)
    def test_request_raises_config_error_when_disabled(self):
        with self.assertRaises(discord.DiscordConfigError):
            discord._request("GET", "/anything")
