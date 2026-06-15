from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import SanctionRecord, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-created_at",)
    list_display = (
        "discord_name",
        "discord_id",
        "riot_id",
        "rank_solo",
        "status",
        "is_staff",
        "created_at",
    )
    list_filter = ("status", "is_staff", "is_superuser", "vc_style")
    search_fields = ("discord_id", "discord_name", "riot_game_name", "riot_puuid")
    readonly_fields = (
        "discord_created_at",
        "rank_solo",
        "rank_flex",
        "rank_fetched_at",
        "last_login",
        "created_at",
    )

    fieldsets = (
        (None, {"fields": ("discord_id", "password")}),
        ("Discord", {"fields": ("discord_name", "discord_created_at", "avatar_url")}),
        ("Riot", {"fields": ("riot_game_name", "riot_tagline", "riot_puuid")}),
        ("ランク(自動取得)", {"fields": ("rank_solo", "rank_flex", "rank_fetched_at")}),
        ("プロフィール", {"fields": ("lanes", "play_hours", "vc_style", "bio")}),
        ("状態", {"fields": ("status", "terms_agreed_at", "profile_completed", "is_active", "deleted_at")}),
        ("権限", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("日時", {"fields": ("last_login", "created_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("discord_id", "password1", "password2", "is_staff", "is_superuser"),
            },
        ),
    )


@admin.register(SanctionRecord)
class SanctionRecordAdmin(admin.ModelAdmin):
    list_display = ("discord_id", "type", "created_at")
    list_filter = ("type",)
    search_fields = ("discord_id", "reason")
    readonly_fields = ("created_at",)
