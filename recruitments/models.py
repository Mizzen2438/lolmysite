from django.conf import settings
from django.db import models
from django.utils import timezone

from games.models import Game


class Recruitment(models.Model):
    """A party recruitment post (F-REC). Slots model the lanes being filled."""

    class Status(models.TextChoices):
        OPEN = "open", "募集中"
        FILLED = "filled", "成立"
        CLOSED = "closed", "締切"
        EXPIRED = "expired", "期限切れ"

    # Predefined atmosphere tags (F-REC-03); free-text tags are not allowed.
    TAG_CHOICES = [
        ("ガチ", "ガチ"),
        ("エンジョイ", "エンジョイ"),
        ("初心者歓迎", "初心者歓迎"),
        ("聞き専OK", "聞き専OK"),
        ("社会人", "社会人"),
        ("学生", "学生"),
        ("深夜帯", "深夜帯"),
    ]

    game = models.ForeignKey(Game, on_delete=models.PROTECT, related_name="recruitments")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recruitments"
    )
    mode = models.CharField("ゲームモード", max_length=64)
    # Rank band stored as indexes into Game.rank_tiers; null = 指定なし.
    rank_min_idx = models.PositiveSmallIntegerField("対象ランク下限", null=True, blank=True)
    rank_max_idx = models.PositiveSmallIntegerField("対象ランク上限", null=True, blank=True)
    start_at = models.DateTimeField("開始予定時刻")
    duration_label = models.CharField("想定プレイ時間", max_length=32, blank=True)
    vc_required = models.BooleanField("VC 必須", default=True)
    vc_tool = models.CharField("VC 種別", max_length=64, blank=True)
    tags = models.JSONField("雰囲気タグ", default=list, blank=True)
    comment = models.TextField("コメント", blank=True)
    # Shown only to the owner / approved participants (F-DSC-02, N-06).
    discord_invite_url = models.URLField("Discord 招待リンク", blank=True)
    status = models.CharField(
        "状態", max_length=16, choices=Status.choices, default=Status.OPEN
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "募集"
        verbose_name_plural = "募集"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "start_at"])]

    def __str__(self) -> str:
        return f"{self.mode} / {self.owner} ({self.get_status_display()})"

    # --- display helpers ---

    def rank_range_display(self) -> str:
        tiers = self.game.rank_tiers or []
        if self.rank_min_idx is None and self.rank_max_idx is None:
            return "指定なし"
        lo = tiers[self.rank_min_idx] if self.rank_min_idx is not None else tiers[0]
        hi = tiers[self.rank_max_idx] if self.rank_max_idx is not None else tiers[-1]
        return lo if lo == hi else f"{lo}〜{hi}"

    @property
    def total_slots(self) -> int:
        return self.slots.count()

    @property
    def filled_count(self) -> int:
        return self.slots.filter(member__isnull=False).count()

    def open_lanes(self) -> list[str]:
        return list(self.slots.filter(member__isnull=True).values_list("lane", flat=True))

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.OPEN

    def is_owner(self, user) -> bool:
        return user.is_authenticated and user.pk == self.owner_id

    def can_view_invite(self, user) -> bool:
        """Invite link is visible to the owner and approved participants."""
        if not self.discord_invite_url or not user.is_authenticated:
            return False
        if user.pk == self.owner_id:
            return True
        return self.slots.filter(member_id=user.pk).exists()


class RecruitmentSlot(models.Model):
    """A single lane slot within a recruitment; member is null while open."""

    recruitment = models.ForeignKey(
        Recruitment, on_delete=models.CASCADE, related_name="slots"
    )
    lane = models.CharField("レーン", max_length=16)
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="joined_slots",
    )

    class Meta:
        verbose_name = "募集枠"
        verbose_name_plural = "募集枠"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.lane} ({'埋' if self.member_id else '空'})"


def expire_due_recruitments() -> int:
    """Mark open recruitments whose start time has passed as expired (F-REC-05)."""
    return Recruitment.objects.filter(
        status=Recruitment.Status.OPEN, start_at__lt=timezone.now()
    ).update(status=Recruitment.Status.EXPIRED)
