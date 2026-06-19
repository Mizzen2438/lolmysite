"""Expire open recruitments past their start time (F-REC-05).

Schedule this every minute via Render Cron Job / Celery Beat / system cron:

    python manage.py expire_recruitments
"""

from django.core.management.base import BaseCommand

from recruitments.models import expire_due_recruitments


class Command(BaseCommand):
    help = "開始時刻を過ぎた募集中の募集を期限切れにする"

    def handle(self, *args, **options):
        count = expire_due_recruitments()
        self.stdout.write(self.style.SUCCESS(f"期限切れにした募集: {count} 件"))
