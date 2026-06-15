from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView


def healthz(_request):
    """Lightweight liveness probe for hosting platforms."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    # Public legal pages (no login) — required for the Riot API review.
    path("terms/", TemplateView.as_view(template_name="pages/terms.html"), name="legal_terms"),
    path("privacy/", TemplateView.as_view(template_name="pages/privacy.html"), name="legal_privacy"),
    path("accounts/", include("allauth.urls")),
    path("", include("recruitments.urls")),
    path("", include("applications.urls")),
    path("", include("notifications.urls")),
    path("", include("moderation.urls")),
    path("", include("accounts.urls")),
]
