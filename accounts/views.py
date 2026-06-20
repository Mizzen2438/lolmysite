from __future__ import annotations

import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import rso
from .forms import ProfileForm, RiotLinkForm
from .services import (
    RiotLinkError,
    can_refresh,
    complete_rso_link,
    link_riot_account,
    refresh_rank,
)

User = get_user_model()

# Session keys for the RSO OAuth2 round-trip (CSRF state + id_token nonce).
RSO_STATE_KEY = "rso_state"
RSO_NONCE_KEY = "rso_nonce"


def home(request):
    return render(request, "home.html")


def login_view(request):
    """Landing page with the 'Sign in with Discord' button."""
    if request.user.is_authenticated:
        return redirect("post_login")
    return render(request, "accounts/login.html", {"dev_login_enabled": settings.DEV_LOGIN_ENABLED})


def dev_login(request):
    """Passwordless login for local demos only (bypasses Discord OAuth).

    Disabled unless settings.DEV_LOGIN_ENABLED (defaults to DEBUG); returns 404
    otherwise so it can never be reached in production.
    """
    if not settings.DEV_LOGIN_ENABLED:
        raise Http404()
    if request.method == "POST":
        user = get_object_or_404(User, pk=request.POST.get("user_id"), is_active=True)
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("post_login")
    users = User.objects.filter(is_superuser=False, is_active=True).order_by("discord_name")
    return render(request, "accounts/dev_login.html", {"users": users})


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
            messages.success(request, "プロフィールを保存しました。次に Riot ID を連携しましょう。")
            return redirect("riot_link")
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
def riot_link(request):
    """Link a Riot account (F-ACC-03/06, F-UNIQ-03).

    When RSO is enabled, ownership is verified via Riot sign-in (riot_rso_login)
    and the manual Riot ID form is disabled. Otherwise we fall back to the
    unverified manual entry.
    """
    rso_enabled = rso.is_enabled()
    if request.method == "POST" and not rso_enabled:
        form = RiotLinkForm(request.POST)
        if form.is_valid():
            try:
                link_riot_account(
                    request.user,
                    form.cleaned_data["game_name"],
                    form.cleaned_data["tagline"],
                )
            except RiotLinkError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Riot ID を連携し、ランクを取得しました。")
                return redirect("mypage")
    else:
        form = RiotLinkForm()
    return render(
        request, "accounts/riot_link.html", {"form": form, "rso_enabled": rso_enabled}
    )


@login_required
def riot_rso_login(request):
    """Start RSO sign-in: redirect the user to Riot to authenticate (F-ACC-09)."""
    if not rso.is_enabled():
        raise Http404()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    request.session[RSO_STATE_KEY] = state
    request.session[RSO_NONCE_KEY] = nonce
    redirect_uri = request.build_absolute_uri(reverse("riot_rso_callback"))
    return redirect(rso.build_authorize_url(redirect_uri, state, nonce))


@login_required
def riot_rso_callback(request):
    """RSO redirect target: verify the sign-in and link the proven account."""
    if not rso.is_enabled():
        raise Http404()

    state = request.session.pop(RSO_STATE_KEY, None)
    nonce = request.session.pop(RSO_NONCE_KEY, None)

    if request.GET.get("error"):
        messages.error(request, "Riot ログインがキャンセルされました。")
        return redirect("riot_link")
    if not state or request.GET.get("state") != state:
        messages.error(request, "セッションが無効です。最初からやり直してください。")
        return redirect("riot_link")
    code = request.GET.get("code")
    if not code:
        messages.error(request, "認可コードが取得できませんでした。")
        return redirect("riot_link")

    redirect_uri = request.build_absolute_uri(reverse("riot_rso_callback"))
    try:
        tokens = rso.exchange_code(code, redirect_uri)
        puuid = rso.extract_puuid(tokens.get("id_token", ""), nonce=nonce)
        complete_rso_link(request.user, puuid)
    except (rso.RsoError, RiotLinkError) as exc:
        messages.error(request, f"Riot 連携に失敗しました: {exc}")
        return redirect("riot_link")

    messages.success(request, "Riot アカウントの所有を確認し、連携しました。")
    return redirect("mypage")


@login_required
@require_POST
def riot_refresh(request):
    """Manually re-fetch the current user's rank (cooldown enforced)."""
    try:
        refresh_rank(request.user)
    except RiotLinkError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "ランクを更新しました。")
    return redirect("mypage")


@login_required
def mypage(request):
    my_recruitments = request.user.recruitments.prefetch_related("slots").all()[:20]
    my_applications = (
        request.user.applications.select_related("recruitment")
        .exclude(status__in=["withdrawn", "rejected"])
        .all()[:20]
    )
    return render(
        request,
        "accounts/mypage.html",
        {
            "can_refresh": can_refresh(request.user),
            "my_recruitments": my_recruitments,
            "my_applications": my_applications,
        },
    )
