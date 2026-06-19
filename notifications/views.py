from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notification_list(request):
    notifications = request.user.notifications.all()[:100]
    # Mark everything as read once the user opens the list.
    request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    return render(request, "notifications/list.html", {"notifications": notifications})


@login_required
@require_POST
def mark_all_read(request):
    request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    return redirect("notification_list")


def unread_count(request):
    """Context processor: unread notification count for the header badge."""
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return {
            "unread_notifications": Notification.objects.filter(
                user=user, read_at__isnull=True
            ).count()
        }
    return {"unread_notifications": 0}
