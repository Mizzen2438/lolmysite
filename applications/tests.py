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
