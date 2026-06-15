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
