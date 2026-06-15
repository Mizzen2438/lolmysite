"""Redirect authenticated users through onboarding until it is complete.

Flow (ARCHITECTURE.md §5.1 step 5):
    login → terms agreement (F-SAFE-06) → profile setup → app

Staff/superusers and a small allow-list of paths (the onboarding pages
themselves, logout, admin, static, health) are exempt so users never get
trapped in a redirect loop.
"""

from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse


class OnboardingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and not user.is_staff:
            target = self._required_step(request, user)
            if target and request.path != target:
                return redirect(target)
        return self.get_response(request)

    def _required_step(self, request, user):
        # Never interfere with these paths.
        exempt_prefixes = (
            reverse("terms"),
            reverse("profile_setup"),
            "/accounts/",  # allauth (login/logout/callback)
            "/admin/",
            "/static/",
            "/healthz",
            reverse("legal_terms"),
            reverse("legal_privacy"),
        )
        if request.path.startswith(exempt_prefixes):
            return None

        if user.terms_agreed_at is None:
            return reverse("terms")
        if not user.profile_completed:
            return reverse("profile_setup")
        return None
