from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Block, Report


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("user", "blocked_user", "created_at")
    raw_id_fields = ("user", "blocked_user")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "target_type", "target_link", "reason", "status", "reporter", "created_at")
    list_filter = ("status", "target_type", "reason")
    search_fields = ("detail", "reporter__discord_name")
    readonly_fields = ("reporter", "target_type", "target_id", "reason", "detail", "created_at", "target_link")
    actions = ["mark_reviewing", "mark_resolved", "mark_dismissed"]

    @admin.display(description="対象")
    def target_link(self, obj):
        target = obj.target()
        return format_html("{}", str(target)) if target else "(削除済み)"

    def _set_status(self, request, queryset, status):
        updated = queryset.update(status=status, handled_by=request.user, handled_at=timezone.now())
        self.message_user(request, f"{updated} 件を更新しました。")

    @admin.action(description="確認中にする")
    def mark_reviewing(self, request, queryset):
        self._set_status(request, queryset, Report.Status.REVIEWING)

    @admin.action(description="対応済みにする")
    def mark_resolved(self, request, queryset):
        self._set_status(request, queryset, Report.Status.RESOLVED)

    @admin.action(description="却下する")
    def mark_dismissed(self, request, queryset):
        self._set_status(request, queryset, Report.Status.DISMISSED)
