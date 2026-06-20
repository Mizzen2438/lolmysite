from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ProfileForm, RiotLinkForm
from .services import (
    RiotLinkError,
    begin_riot_link,
    can_refresh,
    complete_riot_link,
    refresh_rank,
)

User = get_user_model()

# Session key + lifetime for the in-progress Riot ownership verification.
RIOT_LINK_SESSION_KEY = "riot_link_pending"
RIOT_LINK_TTL_SECONDS = 15 * 60


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
    """Step 1 of linking: enter a Riot ID and get a verification code (F-UNIQ-03).

    Ownership is proven in :func:`riot_verify`; nothing is saved here.
    """
    if request.method == "POST":
        form = RiotLinkForm(request.POST)
        if form.is_valid():
            try:
                pending = begin_riot_link(
                    request.user,
                    form.cleaned_data["game_name"],
                    form.cleaned_data["tagline"],
                )
            except RiotLinkError as exc:
                messages.error(request, str(exc))
            else:
                pending["ts"] = timezone.now().timestamp()
                request.session[RIOT_LINK_SESSION_KEY] = pending
                return redirect("riot_verify")
    else:
        # Starting over: drop any half-finished verification.
        request.session.pop(RIOT_LINK_SESSION_KEY, None)
        form = RiotLinkForm()
    return render(request, "accounts/riot_link.html", {"form": form})


@login_required
def riot_verify(request):
    """Step 2: confirm the verification code set in the LoL client, then link."""
    pending = request.session.get(RIOT_LINK_SESSION_KEY)
    expired = (
        not pending
        or (timezone.now().timestamp() - pending.get("ts", 0)) > RIOT_LINK_TTL_SECONDS
    )
    if expired:
        request.session.pop(RIOT_LINK_SESSION_KEY, None)
        messages.error(request, "確認の有効期限が切れました。最初からやり直してください。")
        return redirect("riot_link")

    if request.method == "POST":
        try:
            complete_riot_link(request.user, pending)
        except RiotLinkError as exc:
            messages.error(request, str(exc))
        else:
            request.session.pop(RIOT_LINK_SESSION_KEY, None)
            messages.success(request, "Riot ID の所有を確認し、連携してランクを取得しました。")
            return redirect("mypage")

    return render(
        request,
        "accounts/riot_verify.html",
        {
            "code": pending["code"],
            "riot_id": f"{pending['game_name']}#{pending['tagline']}",
        },
    )


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
