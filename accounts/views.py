from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import ProfileForm


def home(request):
    return render(request, "home.html")


def login_view(request):
    """Landing page with the 'Sign in with Discord' button."""
    if request.user.is_authenticated:
        return redirect("post_login")
    return render(request, "accounts/login.html")


@login_required
def post_login(request):
    """Dispatch a freshly-authenticated user to the right next step."""
    user = request.user
    if user.terms_agreed_at is None:
        return redirect("terms")
    if not user.profile_completed:
        return redirect("profile_setup")
    return redirect("mypage")


@login_required
def terms(request):
    """Terms / community guidelines agreement (F-SAFE-06)."""
    if request.method == "POST":
        if request.POST.get("agree"):
            request.user.terms_agreed_at = timezone.now()
            request.user.save(update_fields=["terms_agreed_at"])
            return redirect("profile_setup")
        messages.error(request, "続行するには利用規約への同意が必要です。")
    return render(request, "accounts/terms.html")


@login_required
def profile_setup(request):
    """Initial profile setup; redirects to Riot linking afterwards (M3)."""
    if request.user.terms_agreed_at is None:
        return redirect("terms")

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user.profile_completed = True
            user.save()
            messages.success(request, "プロフィールを保存しました。")
            return redirect("mypage")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile_form.html", {"form": form, "setup": True})


@login_required
def profile_edit(request):
    """Edit profile after onboarding."""
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "プロフィールを更新しました。")
            return redirect("mypage")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile_form.html", {"form": form, "setup": False})


@login_required
def mypage(request):
    return render(request, "accounts/mypage.html", {"riot_link_url": reverse("profile_edit")})
