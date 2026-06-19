from django.conf import settings
from django.db import models


class Notification(models.Model):
    """In-app notification (F-NTF). MVP delivers on-site only; Discord DM later."""

    class Type(models.TextChoices):
        APPLICATION_RECEIVED = "application_received", "新しい応募"
        APPLICATION_APPROVED = "application_approved", "応募が承認されました"
        APPLICATION_REJECTED = "application_rejected", "応募が見送られました"
        PARTICIPANT_LEFT = "participant_left", "参加者が辞退しました"
        RECRUITMENT_FILLED = "recruitment_filled", "募集が成立しました"
        RECRUITMENT_CLOSED = "recruitment_closed", "募集が締め切られました"
        RECRUITMENT_DELETED = "recruitment_deleted", "募集が削除されました"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField("種別", max_length=32, choices=Type.choices)
    # Free-form payload, e.g. {"recruitment_id": 1, "message": "..."}.
    payload = models.JSONField("内容", default=dict, blank=True)
    read_at = models.DateTimeField("既読日時", null=True, blank=True)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)

    class Meta:
        verbose_name = "通知"
        verbose_name_plural = "通知"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]

    def __str__(self) -> str:
        return f"{self.get_type_display()} -> {self.user}"

    @property
    def message(self) -> str:
        return self.payload.get("message", self.get_type_display())

    @property
    def recruitment_id(self):
        return self.payload.get("recruitment_id")


def notify(user, type, *, message="", recruitment_id=None, **extra) -> Notification:
    """Create an in-app notification for ``user``."""
    payload = {"message": message, **extra}
    if recruitment_id is not None:
        payload["recruitment_id"] = recruitment_id
    return Notification.objects.create(user=user, type=type, payload=payload)
