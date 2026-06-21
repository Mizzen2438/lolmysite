"""Periodic rank refresh for active users (F-ACC-08, ARCHITECTURE.md §5.2).

Run on a schedule (Render Cron Job / Celery Beat / system cron), e.g. daily:

    python manage.py refresh_ranks

Only users who logged in within --active-days are refreshed, and requests are
spaced out to respect the Riot API rate limit (N-13).
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts import riot
from accounts.models import User
from accounts.services import RiotLinkError, refresh_rank


class Command(BaseCommand):
    help = "アクティブユーザーの LoL ランクを Riot API から再取得する"

    def add_arguments(self, parser):
        parser.add_argument("--active-days", type=int, default=7)
        parser.add_argument(
            "--sleep", type=float, default=1.2,
            help="リクエスト間の待機秒数(レートリミット対策)",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timezone.timedelta(days=options["active_days"])
        users = User.objects.filter(
            riot_puuid__isnull=False,
            deleted_at__isnull=True,
            last_login__gte=cutoff,
        )

        updated = failed = 0
        for user in users.iterator():
            try:
                refresh_rank(user, force=True)
                updated += 1
            except RiotLinkError as exc:
                # refresh_rank now surfaces Riot API failures as RiotLinkError;
                # recover the original cause to keep honouring Retry-After.
                cause = exc.__cause__
                if isinstance(cause, riot.RiotRateLimited):
                    self.stderr.write(f"レート制限。{cause.retry_after}s 待機します。")
                    time.sleep(cause.retry_after)
                else:
                    failed += 1
                    self.stderr.write(f"{user.discord_id}: {exc}")
            except Exception as exc:  # noqa: BLE001 - keep going on per-user errors
                failed += 1
                self.stderr.write(f"{user.discord_id}: {exc}")
            time.sleep(options["sleep"])

        self.stdout.write(
            self.style.SUCCESS(f"完了: 更新 {updated} 件 / 失敗 {failed} 件")
        )
