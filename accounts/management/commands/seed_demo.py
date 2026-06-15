"""Seed local demo data so the full flow can be tried without Discord/Riot.

    python manage.py seed_demo

Creates the LoL game master, a handful of onboarded demo users (with fake
Riot links and ranks) and a few recruitments, including one pending
application. Intended for local development only.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from applications import services as application_services
from games.models import Game
from recruitments.models import Recruitment, RecruitmentSlot

DEMO_USERS = [
    # discord_id, name, solo rank, lanes
    ("900000000000000001", "デモ太郎", "ゴールド II", ["TOP", "MID"]),
    ("900000000000000002", "デモ花子", "シルバー III", ["SUP"]),
    ("900000000000000003", "デモ次郎", "プラチナ IV", ["ADC"]),
    ("900000000000000004", "デモ三郎", "ゴールド IV", ["JG", "MID"]),
]


class Command(BaseCommand):
    help = "ローカルデモ用のサンプルデータ(ユーザー・募集)を投入する"

    def handle(self, *args, **options):
        game = self._ensure_game()
        users = {name: self._ensure_user(did, name, rank, lanes, game)
                 for did, name, rank, lanes in DEMO_USERS}

        if Recruitment.objects.filter(owner__discord_id__startswith="9000000000000000").exists():
            self.stdout.write("デモ募集は既に存在します。ユーザーのみ確認しました。")
            self.stdout.write(self.style.SUCCESS(f"デモユーザー {len(users)} 名を用意しました。"))
            return

        tiers = game.rank_tiers

        # 1) 太郎のフレックス募集(MID/ADC 募集中)+ 次郎が MID に応募中
        rec1 = self._recruitment(
            game, users["デモ太郎"], "ランク(フレックス)",
            rank=("ゴールド", "プラチナ", tiers), start_in_h=3,
            vc="Discord VC(聞き専OK)", tags=["エンジョイ", "聞き専OK"],
            comment="フレックス回せる方募集!勝ち負けより楽しく。",
            invite="https://discord.gg/demo-flex",
            owner_lane="TOP", open_lanes=["MID", "ADC"],
        )
        application_services.apply(users["デモ次郎"], rec1, "ADC", "22時から参加できます!")

        # 2) 花子のデュオ募集(ADC 募集中)
        self._recruitment(
            game, users["デモ花子"], "ランク(デュオ)",
            rank=("シルバー", "シルバー", tiers), start_in_h=2,
            vc="なし(ゲーム内チャットのみ)", tags=["ガチ"],
            comment="サポメインです。ADC の方デュオしましょう。",
            invite="", owner_lane="SUP", open_lanes=["ADC"],
        )

        # 3) 三郎の ARAM 募集(FILL 4 枠)
        self._recruitment(
            game, users["デモ三郎"], "ARAM",
            rank=(None, None, tiers), start_in_h=5,
            vc="Discord VC(聞き専OK)", tags=["エンジョイ", "初心者歓迎", "深夜帯"],
            comment="寝る前に ARAM やりましょう〜。初心者歓迎!",
            invite="https://discord.gg/demo-aram", owner_lane="FILL",
            open_lanes=[], fill=4,
        )

        self.stdout.write(self.style.SUCCESS(
            f"デモデータを投入しました: ユーザー {len(users)} 名 / 募集 3 件。"
            " /dev-login/ からログインして試せます。"
        ))

    def _ensure_game(self) -> Game:
        game, created = Game.objects.get_or_create(
            slug="league-of-legends",
            defaults={
                "name": "League of Legends",
                "modes": ["ランク(フレックス)", "ランク(デュオ)", "ノーマル(ドラフト)", "ARAM", "カスタム"],
                "lanes": ["TOP", "JG", "MID", "ADC", "SUP", "FILL"],
                "rank_tiers": ["アイアン", "ブロンズ", "シルバー", "ゴールド", "プラチナ",
                               "エメラルド", "ダイヤモンド", "マスター", "グランドマスター", "チャレンジャー"],
            },
        )
        return game

    def _ensure_user(self, discord_id, name, rank, lanes, game) -> User:
        user, _ = User.objects.get_or_create(
            discord_id=discord_id,
            defaults={
                "discord_name": name,
                "riot_puuid": f"DEMO-{discord_id}",
                "riot_game_name": name,
                "riot_tagline": "JP1",
                "rank_solo": rank,
                "rank_flex": rank,
                "rank_fetched_at": timezone.now(),
                "lanes": lanes,
                "vc_style": User.VCStyle.TALK,
                "terms_agreed_at": timezone.now(),
                "profile_completed": True,
            },
        )
        return user

    def _recruitment(self, game, owner, mode, *, rank, start_in_h, vc, tags,
                     comment, invite, owner_lane, open_lanes, fill=0) -> Recruitment:
        lo_name, hi_name, tiers = rank
        rec = Recruitment.objects.create(
            game=game, owner=owner, mode=mode,
            rank_min_idx=tiers.index(lo_name) if lo_name else None,
            rank_max_idx=tiers.index(hi_name) if hi_name else None,
            start_at=timezone.now() + timedelta(hours=start_in_h),
            duration_label="2〜3時間", vc_tool=vc, vc_required="必須" in vc,
            tags=tags, comment=comment, discord_invite_url=invite,
        )
        RecruitmentSlot.objects.create(recruitment=rec, lane=owner_lane, member=owner)
        for lane in open_lanes:
            RecruitmentSlot.objects.create(recruitment=rec, lane=lane)
        for _ in range(fill):
            RecruitmentSlot.objects.create(recruitment=rec, lane="FILL")
        return rec
