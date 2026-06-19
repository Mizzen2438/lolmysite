from django.conf import settings
from django.db import models
from django.db.models import Q


class Block(models.Model):
    """A user blocking another user (F-SAFE-02).

    Full block management UI lands in M6; the model exists now so the
    application eligibility check can honour blocks.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocking"
    )
    blocked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocked_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ブロック"
        verbose_name_plural = "ブロック"
        constraints = [
            models.UniqueConstraint(fields=["user", "blocked_user"], name="unique_block")
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.blocked_user}"

    @staticmethod
    def exists_between(a, b) -> bool:
        """Whether either user has blocked the other."""
        return Block.objects.filter(
            Q(user=a, blocked_user=b) | Q(user=b, blocked_user=a)
        ).exists()


class Report(models.Model):
    """A user report against another user or a recruitment (F-SAFE-01)."""

    class TargetType(models.TextChoices):
        USER = "user", "ユーザー"
        RECRUITMENT = "recruitment", "募集"

    class Reason(models.TextChoices):
        HARASSMENT = "harassment", "暴言・ハラスメント"
        SMURF = "smurf", "サブ垢・スマーフの疑い"
        NO_SHOW = "no_show", "無断キャンセル"
        INAPPROPRIATE = "inappropriate", "不適切な内容"
        OTHER = "other", "その他"

    class Status(models.TextChoices):
        OPEN = "open", "未対応"
        REVIEWING = "reviewing", "確認中"
        RESOLVED = "resolved", "対応済み"
        DISMISSED = "dismissed", "却下"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="reports_made"
    )
    target_type = models.CharField("対象種別", max_length=16, choices=TargetType.choices)
    target_id = models.PositiveIntegerField("対象ID")
    reason = models.CharField("理由", max_length=16, choices=Reason.choices)
    detail = models.TextField("詳細", blank=True)
    status = models.CharField("状態", max_length=16, choices=Status.choices, default=Status.OPEN)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reports_handled",
    )
    handled_at = models.DateTimeField("対応日時", null=True, blank=True)
    created_at = models.DateTimeField("通報日時", auto_now_add=True)

    class Meta:
        verbose_name = "通報"
        verbose_name_plural = "通報"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_target_type_display()}#{self.target_id} - {self.get_reason_display()}"

    def target(self):
        """Resolve the reported object for admin display."""
        if self.target_type == self.TargetType.USER:
            from accounts.models import User

            return User.objects.filter(pk=self.target_id).first()
        from recruitments.models import Recruitment

        return Recruitment.objects.filter(pk=self.target_id).first()
