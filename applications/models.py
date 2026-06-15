from django.conf import settings
from django.db import models

from recruitments.models import Recruitment


class Application(models.Model):
    """An application to join a recruitment (F-APP)."""

    class Status(models.TextChoices):
        PENDING = "pending", "応募中"
        APPROVED = "approved", "承認"
        REJECTED = "rejected", "見送り"
        WITHDRAWN = "withdrawn", "取り下げ"
        DECLINED = "declined", "辞退"

    ACTIVE_STATUSES = (Status.PENDING, Status.APPROVED)

    recruitment = models.ForeignKey(
        Recruitment, on_delete=models.CASCADE, related_name="applications"
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications"
    )
    desired_lane = models.CharField("希望レーン", max_length=16)
    comment = models.TextField("コメント", blank=True)
    status = models.CharField(
        "状態", max_length=16, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField("応募日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "応募"
        verbose_name_plural = "応募"
        ordering = ["-created_at"]
        constraints = [
            # One application row per (recruitment, applicant); re-applying
            # after withdrawal/rejection reuses the same row (F-APP-05).
            models.UniqueConstraint(
                fields=["recruitment", "applicant"], name="unique_application"
            )
        ]

    def __str__(self) -> str:
        return f"{self.applicant} -> {self.recruitment_id} ({self.get_status_display()})"

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES
