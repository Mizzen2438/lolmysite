from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView


def healthz(_request):
    """Lightweight liveness probe for hosting platforms."""
    return JsonResponse({"status": "ok"})


def riot_txt(_request):
    """Serve the Riot API domain-verification code at /riot.txt (N-14).

    The exact code is provided per application and set via the
    RIOT_VERIFICATION_CODE environment variable. The body must contain only
    the code, nothing else.
    """
    return HttpResponse(settings.RIOT_VERIFICATION_CODE, content_type="text/plain")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("riot.txt", riot_txt, name="riot_txt"),
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
