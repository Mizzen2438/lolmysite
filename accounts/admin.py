from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import SanctionRecord, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    actions = ["warn_users", "suspend_users", "unsuspend_users"]
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

    @admin.action(description="選択したユーザーに警告を出す")
    def warn_users(self, request, queryset):
        for user in queryset:
            SanctionRecord.objects.create(
                discord_id=user.discord_id, type=SanctionRecord.Type.WARNING,
                reason="管理画面からの警告",
            )
            user.status = User.Status.WARNED
            user.save(update_fields=["status"])
        self.message_user(request, f"{queryset.count()} 名に警告を出しました。")

    @admin.action(description="選択したユーザーを凍結する")
    def suspend_users(self, request, queryset):
        # Suspension is recorded by discord_id so it survives account deletion
        # and blocks re-registration via the social adapter (F-UNIQ-04).
        for user in queryset:
            SanctionRecord.objects.create(
                discord_id=user.discord_id, type=SanctionRecord.Type.SUSPENSION,
                reason="管理画面からの凍結",
            )
            user.status = User.Status.SUSPENDED
            user.is_active = False
            user.save(update_fields=["status", "is_active"])
        self.message_user(request, f"{queryset.count()} 名を凍結しました。")

    @admin.action(description="選択したユーザーの凍結を解除する")
    def unsuspend_users(self, request, queryset):
        for user in queryset:
            SanctionRecord.objects.filter(
                discord_id=user.discord_id, type=SanctionRecord.Type.SUSPENSION
            ).delete()
            user.status = User.Status.ACTIVE
            user.is_active = True
            user.save(update_fields=["status", "is_active"])
        self.message_user(request, f"{queryset.count()} 名の凍結を解除しました。")


@admin.register(SanctionRecord)
class SanctionRecordAdmin(admin.ModelAdmin):
    list_display = ("discord_id", "type", "created_at")
    list_filter = ("type",)
    search_fields = ("discord_id", "reason")
    readonly_fields = ("created_at",)
