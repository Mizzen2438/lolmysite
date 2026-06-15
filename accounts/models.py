from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user identified by Discord account (F-ACC, F-UNIQ).

    Authentication is via Discord OAuth; ``discord_id`` is the unique natural
    key. Rank fields are populated only from the Riot API (F-ACC-06) — there
    is intentionally no self-service path to edit them.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "アクティブ"
        WARNED = "warned", "警告中"
        SUSPENDED = "suspended", "凍結"

    class VCStyle(models.TextChoices):
        TALK = "talk", "通話OK"
        LISTEN_ONLY = "listen_only", "聞き専"
        TEXT_ONLY = "text_only", "テキストのみ"
        UNSET = "unset", "未設定"

    # --- Identity (F-UNIQ-02) ---
    discord_id = models.CharField("Discord ID", max_length=32, unique=True)
    discord_created_at = models.DateTimeField(
        "Discord アカウント作成日時", null=True, blank=True,
        help_text="Snowflake から算出(F-UNIQ-07)",
    )
    discord_name = models.CharField("Discord 名", max_length=100, blank=True)
    avatar_url = models.URLField("アバターURL", blank=True)

    # --- Riot account (F-ACC-03, F-UNIQ-03) ---
    riot_game_name = models.CharField("Riot ゲーム名", max_length=64, blank=True)
    riot_tagline = models.CharField("Riot タグライン", max_length=16, blank=True)
    riot_puuid = models.CharField(
        "Riot PUUID", max_length=128, unique=True, null=True, blank=True,
        help_text="一意。未連携の間は NULL(F-UNIQ-03)",
    )

    # --- Rank (Riot API only, F-ACC-06/08) ---
    rank_solo = models.CharField("ランク(ソロ)", max_length=32, blank=True)
    rank_flex = models.CharField("ランク(フレックス)", max_length=32, blank=True)
    rank_fetched_at = models.DateTimeField("ランク取得日時", null=True, blank=True)

    # --- Profile (F-ACC-04/05) ---
    lanes = models.JSONField("得意レーン", default=list, blank=True)
    play_hours = models.CharField("プレイ時間帯", max_length=200, blank=True)
    vc_style = models.CharField(
        "VC スタイル", max_length=16, choices=VCStyle.choices, default=VCStyle.UNSET
    )
    bio = models.TextField("自己紹介", blank=True)

    # --- Account state ---
    status = models.CharField(
        "状態", max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    terms_agreed_at = models.DateTimeField(
        "規約同意日時", null=True, blank=True, help_text="F-SAFE-06"
    )

    # --- Django flags ---
    is_staff = models.BooleanField("スタッフ権限", default=False)
    is_active = models.BooleanField("有効", default=True)

    created_at = models.DateTimeField("登録日時", auto_now_add=True)
    deleted_at = models.DateTimeField(
        "退会日時", null=True, blank=True, help_text="退会は論理削除(F-ACC-07)"
    )

    objects = UserManager()

    USERNAME_FIELD = "discord_id"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "ユーザー"
        verbose_name_plural = "ユーザー"

    def __str__(self) -> str:
        return self.discord_name or f"Discord:{self.discord_id}"

    @property
    def riot_id(self) -> str:
        """Human-readable Riot ID (GameName#TagLine), or empty if unlinked."""
        if self.riot_game_name and self.riot_tagline:
            return f"{self.riot_game_name}#{self.riot_tagline}"
        return ""

    @property
    def is_riot_linked(self) -> bool:
        return bool(self.riot_puuid)


class SanctionRecord(models.Model):
    """Warning / suspension history keyed by Discord ID (F-UNIQ-04).

    Stored by ``discord_id`` rather than a FK so the history survives account
    deletion and is re-applied if the same Discord account re-registers.
    """

    class Type(models.TextChoices):
        WARNING = "warning", "警告"
        SUSPENSION = "suspension", "凍結"

    discord_id = models.CharField("Discord ID", max_length=32, db_index=True)
    type = models.CharField("種別", max_length=16, choices=Type.choices)
    reason = models.TextField("理由")
    created_at = models.DateTimeField("発行日時", auto_now_add=True)

    class Meta:
        verbose_name = "制裁記録"
        verbose_name_plural = "制裁記録"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_type_display()} / {self.discord_id}"
