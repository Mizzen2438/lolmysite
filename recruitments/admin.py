from django.contrib import admin

from .models import Recruitment, RecruitmentSlot


class RecruitmentSlotInline(admin.TabularInline):
    model = RecruitmentSlot
    extra = 0
    raw_id_fields = ("member",)


@admin.register(Recruitment)
class RecruitmentAdmin(admin.ModelAdmin):
    list_display = ("id", "mode", "owner", "status", "start_at", "created_at")
    list_filter = ("status", "mode", "game")
    search_fields = ("owner__discord_name", "comment")
    raw_id_fields = ("owner",)
    inlines = [RecruitmentSlotInline]
    readonly_fields = ("created_at", "updated_at")
