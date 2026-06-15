from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.adapters import DiscordSocialAccountAdapter
from accounts.admin import UserAdmin
from accounts.models import SanctionRecord
from accounts.models import User as UserModel
from games.models import Game
from recruitments.models import Recruitment, RecruitmentSlot

from .models import Block, Report

User = get_user_model()
BACKEND = "django.contrib.auth.backends.ModelBackend"


def make_game():
    return Game.objects.create(
        name="LoL", slug="league-of-legends", modes=["ランク(フレックス)"],
        lanes=["TOP", "MID"], rank_tiers=["アイアン", "ブロンズ", "シルバー"],
    )


def make_user(discord_id):
    u = User.objects.create_user(discord_id=discord_id, discord_name=discord_id)
    u.terms_agreed_at = timezone.now()
    u.profile_completed = True
    u.save()
    return u


def make_recruitment(owner, game, **kw):
    rec = Recruitment.objects.create(
        game=game, owner=owner, mode="ランク(フレックス)",
        start_at=timezone.now() + timedelta(hours=2), **kw,
    )
    RecruitmentSlot.objects.create(recruitment=rec, lane="TOP", member=owner)
    RecruitmentSlot.objects.create(recruitment=rec, lane="MID")
    return rec


class ReportTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = make_user("owner")
        self.reporter = make_user("reporter")
        self.rec = make_recruitment(self.owner, self.game)

    def test_report_recruitment(self):
        self.client.force_login(self.reporter, backend=BACKEND)
        self.client.post(
            reverse("report_create", args=["recruitment", self.rec.pk]),
            {"reason": "inappropriate", "detail": "不適切です"},
        )
        report = Report.objects.get()
        self.assertEqual(report.target_type, "recruitment")
        self.assertEqual(report.target_id, self.rec.pk)
        self.assertEqual(report.reporter, self.reporter)

    def test_cannot_report_self(self):
        self.client.force_login(self.owner, backend=BACKEND)
        self.client.post(
            reverse("report_create", args=["user", self.owner.pk]),
            {"reason": "other"},
        )
        self.assertEqual(Report.objects.count(), 0)

    def test_smurf_reason_available(self):
        self.assertIn("smurf", dict(Report.Reason.choices))


class BlockTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = make_user("owner")
        self.viewer = make_user("viewer")
        self.rec = make_recruitment(self.owner, self.game)

    def test_block_and_unblock(self):
        self.client.force_login(self.viewer, backend=BACKEND)
        self.client.post(reverse("block_user", args=[self.owner.pk]))
        self.assertTrue(Block.objects.filter(user=self.viewer, blocked_user=self.owner).exists())
        self.client.post(reverse("unblock_user", args=[self.owner.pk]))
        self.assertFalse(Block.objects.filter(user=self.viewer, blocked_user=self.owner).exists())

    def test_blocked_owner_recruitment_hidden_from_list(self):
        Block.objects.create(user=self.viewer, blocked_user=self.owner)
        self.client.force_login(self.viewer, backend=BACKEND)
        resp = self.client.get(reverse("recruitment_list"))
        self.assertNotIn(self.rec.pk, {r.pk for r in resp.context["recruitments"]})


class HiddenRecruitmentTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = make_user("owner")
        self.rec = make_recruitment(self.owner, self.game, is_hidden=True)

    def test_hidden_excluded_from_list(self):
        resp = self.client.get(reverse("recruitment_list"))
        self.assertNotIn(self.rec.pk, {r.pk for r in resp.context["recruitments"]})

    def test_hidden_detail_404_for_anonymous(self):
        resp = self.client.get(reverse("recruitment_detail", args=[self.rec.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_hidden_detail_visible_to_owner(self):
        self.client.force_login(self.owner, backend=BACKEND)
        resp = self.client.get(reverse("recruitment_detail", args=[self.rec.pk]))
        self.assertEqual(resp.status_code, 200)


def _admin_request(user):
    request = RequestFactory().post("/admin/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class SuspendReregisterTests(TestCase):
    """F-SAFE-07 + F-UNIQ-04: admin suspend -> re-registration blocked."""

    def test_suspend_creates_sanction_and_blocks_relogin(self):
        user = make_user("123456789012345678")  # snowflake-shaped, old account
        admin = UserAdmin(UserModel, AdminSite())
        request = _admin_request(user)

        admin.suspend_users(request, UserModel.objects.filter(pk=user.pk))
        user.refresh_from_db()
        self.assertEqual(user.status, UserModel.Status.SUSPENDED)
        self.assertFalse(user.is_active)
        self.assertTrue(
            SanctionRecord.objects.filter(
                discord_id=user.discord_id, type=SanctionRecord.Type.SUSPENSION
            ).exists()
        )

        # The social adapter must now block this Discord ID at login.
        adapter = DiscordSocialAccountAdapter()
        sociallogin = SimpleNamespace(
            account=SimpleNamespace(uid=user.discord_id, extra_data={}),
            is_existing=True,
            user=UserModel(),
        )
        with self.assertRaises(ImmediateHttpResponse):
            adapter.pre_social_login(RequestFactory().get("/"), sociallogin)

    def test_unsuspend_clears_sanction(self):
        user = make_user("987654321098765432")
        admin = UserAdmin(UserModel, AdminSite())
        request = _admin_request(user)
        qs = UserModel.objects.filter(pk=user.pk)
        admin.suspend_users(request, qs)
        admin.unsuspend_users(request, qs)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(user.status, UserModel.Status.ACTIVE)
        self.assertFalse(
            SanctionRecord.objects.filter(
                discord_id=user.discord_id, type=SanctionRecord.Type.SUSPENSION
            ).exists()
        )
