from django.contrib import admin

from .models import Recruitment, RecruitmentSlot


class RecruitmentSlotInline(admin.TabularInline):
    model = RecruitmentSlot
    extra = 0
    raw_id_fields = ("member",)


@admin.register(Recruitment)
class RecruitmentAdmin(admin.ModelAdmin):
    list_display = ("id", "mode", "owner", "status", "is_hidden", "start_at", "created_at")
    list_filter = ("status", "is_hidden", "mode", "game")
    search_fields = ("owner__discord_name", "comment")
    raw_id_fields = ("owner",)
    inlines = [RecruitmentSlotInline]
    readonly_fields = ("created_at", "updated_at")
    actions = ["hide_recruitments", "unhide_recruitments"]

    @admin.action(description="選択した募集を非公開にする")
    def hide_recruitments(self, request, queryset):
        updated = queryset.update(is_hidden=True)
        self.message_user(request, f"{updated} 件を非公開にしました。")

    @admin.action(description="選択した募集を公開に戻す")
    def unhide_recruitments(self, request, queryset):
        updated = queryset.update(is_hidden=False)
        self.message_user(request, f"{updated} 件を公開に戻しました。")
