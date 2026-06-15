from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


def healthz(_request):
    """Lightweight liveness probe for hosting platforms."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
]
