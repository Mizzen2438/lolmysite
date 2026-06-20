"""Reconcile and clean up auto-generated Discord match channels (F-DSC-05).

Two phases, both idempotent and safe to run repeatedly:
  - provision: filled recruitments whose channels were not created yet (e.g.
    the in-request best-effort attempt failed) get their temp VC/text channels
    and invite created.
  - cleanup:   recruitments whose ``discord_cleanup_at`` has passed have their
    temporary channels deleted.

Scheduled from GitHub Actions (see .github/workflows/scheduled.yml) because the
free-tier web service has no cron / background worker:

    python manage.py sync_discord_channels
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from applications import discord
from recruitments.models import Recruitment


class Command(BaseCommand):
    help = "成立済み募集の Discord 一時チャンネルを発行/削除する (F-DSC-05)"

    def add_arguments(self, parser):
        parser.add_argument("--provision", action="store_true", help="発行のみ実行")
        parser.add_argument("--cleanup", action="store_true", help="削除のみ実行")

    def handle(self, *args, **options):
        if not settings.DISCORD_BOT_ENABLED:
            self.stdout.write("DISCORD_BOT 連携が無効のためスキップします。")
            return

        # No flag => run both phases.
        do_provision = options["provision"] or not options["cleanup"]
        do_cleanup = options["cleanup"] or not options["provision"]

        if do_provision:
            self._provision_pending()
        if do_cleanup:
            self._cleanup_expired()

    def _provision_pending(self):
        pending = Recruitment.objects.filter(
            status=Recruitment.Status.FILLED, discord_provisioned_at__isnull=True
        )
        created = failed = 0
        for rec in pending:
            try:
                if discord.provision_match_channels(rec):
                    created += 1
            except discord.DiscordError as exc:
                failed += 1
                self.stderr.write(f"発行失敗 (recruitment={rec.pk}): {exc}")
        self.stdout.write(self.style.SUCCESS(f"Discord 発行: 成功 {created} 件 / 失敗 {failed} 件"))

    def _cleanup_expired(self):
        expired = Recruitment.objects.filter(
            discord_cleanup_at__lte=timezone.now(), discord_cleanup_at__isnull=False
        ).exclude(discord_channel_ids=[])
        removed = failed = 0
        for rec in expired:
            try:
                discord.teardown_match_channels(rec)
                removed += 1
            except discord.DiscordError as exc:
                failed += 1
                self.stderr.write(f"削除失敗 (recruitment={rec.pk}): {exc}")
        self.stdout.write(self.style.SUCCESS(f"Discord 削除: 成功 {removed} 件 / 失敗 {failed} 件"))
