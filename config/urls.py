from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthz(_request):
    """Lightweight liveness probe for hosting platforms."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("accounts/", include("allauth.urls")),
    path("", include("recruitments.urls")),
    path("", include("applications.urls")),
    path("", include("notifications.urls")),
    path("", include("accounts.urls")),
]
