from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from games.models import Game

from .forms import RecruitmentCreateForm
from .models import Recruitment, RecruitmentSlot, expire_due_recruitments

User = get_user_model()
BACKEND = "django.contrib.auth.backends.ModelBackend"


def make_game() -> Game:
    return Game.objects.create(
        name="League of Legends",
        slug="league-of-legends",
        modes=["ランク(フレックス)", "ARAM"],
        lanes=["TOP", "JG", "MID", "ADC", "SUP", "FILL"],
        rank_tiers=["アイアン", "ブロンズ", "シルバー", "ゴールド", "プラチナ"],
    )


def onboarded_user(discord_id="owner") -> User:
    user = User.objects.create_user(discord_id=discord_id, discord_name=discord_id)
    user.terms_agreed_at = timezone.now()
    user.profile_completed = True
    user.save()
    return user


def future_str(hours=3) -> str:
    return (timezone.localtime() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")


def make_recruitment(owner, game, **kwargs):
    defaults = dict(
        game=game, owner=owner, mode="ランク(フレックス)",
        start_at=timezone.now() + timedelta(hours=2), comment="よろしく",
    )
    defaults.update(kwargs)
    rec = Recruitment.objects.create(**defaults)
    RecruitmentSlot.objects.create(recruitment=rec, lane="TOP", member=owner)
    RecruitmentSlot.objects.create(recruitment=rec, lane="MID")
    return rec


class ModelTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = onboarded_user()

    def test_rank_range_display(self):
        rec = make_recruitment(self.owner, self.game, rank_min_idx=2, rank_max_idx=4)
        self.assertEqual(rec.rank_range_display(), "シルバー〜プラチナ")
        rec2 = make_recruitment(self.owner, self.game)
        self.assertEqual(rec2.rank_range_display(), "指定なし")

    def test_open_lanes_and_counts(self):
        rec = make_recruitment(self.owner, self.game)
        self.assertEqual(rec.open_lanes(), ["MID"])
        self.assertEqual(rec.filled_count, 1)
        self.assertEqual(rec.total_slots, 2)

    def test_expire_due_recruitments(self):
        past = make_recruitment(self.owner, self.game, start_at=timezone.now() - timedelta(minutes=1))
        future = make_recruitment(self.owner, self.game)
        self.assertEqual(expire_due_recruitments(), 1)
        past.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(past.status, Recruitment.Status.EXPIRED)
        self.assertEqual(future.status, Recruitment.Status.OPEN)


class CreateFormTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = onboarded_user()

    def _data(self, **over):
        data = {
            "mode": "ランク(フレックス)", "my_lane": "TOP",
            "wanted_lanes": ["MID", "ADC"], "additional_slots": 0,
            "rank_min": "2", "rank_max": "4", "start_at": future_str(),
            "duration_label": "2〜3時間", "vc_tool": "Discord VC(聞き専OK)",
            "tags": ["エンジョイ"], "comment": "楽しくやりましょう",
        }
        data.update(over)
        return data

    def test_create_builds_owner_and_open_slots(self):
        form = RecruitmentCreateForm(self._data())
        self.assertTrue(form.is_valid(), form.errors)
        rec = form.create(owner=self.owner)
        self.assertEqual(rec.total_slots, 3)  # owner TOP + MID + ADC
        self.assertEqual(rec.filled_count, 1)
        self.assertEqual(rec.rank_min_idx, 2)
        self.assertTrue(rec.vc_required is False)  # 聞き専OK is not 必須

    def test_additional_fill_slots(self):
        form = RecruitmentCreateForm(self._data(mode="ARAM", wanted_lanes=[], additional_slots=4))
        self.assertTrue(form.is_valid(), form.errors)
        rec = form.create(owner=self.owner)
        self.assertEqual(rec.total_slots, 5)  # owner + 4 FILL

    def test_requires_at_least_one_slot(self):
        form = RecruitmentCreateForm(self._data(wanted_lanes=[], additional_slots=0))
        self.assertFalse(form.is_valid())

    def test_start_must_be_future(self):
        past = (timezone.localtime() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        form = RecruitmentCreateForm(self._data(start_at=past))
        self.assertFalse(form.is_valid())

    def test_rank_min_above_max_rejected(self):
        form = RecruitmentCreateForm(self._data(rank_min="4", rank_max="2"))
        self.assertFalse(form.is_valid())

    @override_settings(NG_WORDS=["死ね"])
    def test_ng_word_rejected(self):
        form = RecruitmentCreateForm(self._data(comment="死ね"))
        self.assertFalse(form.is_valid())


class ListViewTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = onboarded_user()

    def test_filters_by_mode_and_open_only(self):
        make_recruitment(self.owner, self.game, mode="ランク(フレックス)")
        aram = make_recruitment(self.owner, self.game, mode="ARAM")
        closed = make_recruitment(self.owner, self.game, status=Recruitment.Status.CLOSED)

        resp = self.client.get(reverse("recruitment_list"), {"mode": "ARAM"})
        ids = {r.pk for r in resp.context["recruitments"]}
        self.assertEqual(ids, {aram.pk})

        # open=1 by default excludes the closed one.
        resp_all = self.client.get(reverse("recruitment_list"))
        ids_all = {r.pk for r in resp_all.context["recruitments"]}
        self.assertNotIn(closed.pk, ids_all)

    def test_filter_by_rank_band(self):
        in_band = make_recruitment(self.owner, self.game, rank_min_idx=1, rank_max_idx=3)
        out_band = make_recruitment(self.owner, self.game, rank_min_idx=4, rank_max_idx=4)
        resp = self.client.get(reverse("recruitment_list"), {"rank": "2"})
        ids = {r.pk for r in resp.context["recruitments"]}
        self.assertIn(in_band.pk, ids)
        self.assertNotIn(out_band.pk, ids)

    def test_filter_by_open_lane(self):
        rec = make_recruitment(self.owner, self.game)  # open lane MID
        resp = self.client.get(reverse("recruitment_list"), {"lane": "MID"})
        self.assertIn(rec.pk, {r.pk for r in resp.context["recruitments"]})
        resp2 = self.client.get(reverse("recruitment_list"), {"lane": "SUP"})
        self.assertNotIn(rec.pk, {r.pk for r in resp2.context["recruitments"]})


class DetailAndPermissionTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.owner = onboarded_user("owner")
        self.other = onboarded_user("other")
        self.rec = make_recruitment(
            self.owner, self.game, discord_invite_url="https://discord.gg/abc"
        )

    def test_invite_hidden_from_anonymous(self):
        resp = self.client.get(reverse("recruitment_detail", args=[self.rec.pk]))
        self.assertFalse(resp.context["can_view_invite"])
        self.assertNotContains(resp, "discord.gg/abc")

    def test_invite_visible_to_owner(self):
        self.client.force_login(self.owner, backend=BACKEND)
        resp = self.client.get(reverse("recruitment_detail", args=[self.rec.pk]))
        self.assertTrue(resp.context["can_view_invite"])
        self.assertContains(resp, "discord.gg/abc")

    def test_non_owner_cannot_close(self):
        self.client.force_login(self.other, backend=BACKEND)
        self.client.post(reverse("recruitment_close", args=[self.rec.pk]))
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.status, Recruitment.Status.OPEN)

    def test_owner_can_close(self):
        self.client.force_login(self.owner, backend=BACKEND)
        self.client.post(reverse("recruitment_close", args=[self.rec.pk]))
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.status, Recruitment.Status.CLOSED)

    def test_non_owner_cannot_delete(self):
        self.client.force_login(self.other, backend=BACKEND)
        self.client.post(reverse("recruitment_delete", args=[self.rec.pk]))
        self.assertTrue(Recruitment.objects.filter(pk=self.rec.pk).exists())


class ExpireCommandTests(TestCase):
    def test_command_expires(self):
        game = make_game()
        owner = onboarded_user()
        make_recruitment(owner, game, start_at=timezone.now() - timedelta(minutes=5))
        call_command("expire_recruitments")
        self.assertEqual(Recruitment.objects.filter(status=Recruitment.Status.EXPIRED).count(), 1)
