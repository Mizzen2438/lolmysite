from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ProfileForm, RiotLinkForm
from .services import RiotLinkError, can_refresh, link_riot_account, refresh_rank


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
    """Link a Riot ID and pull rank from the Riot API (F-ACC-03/06, F-UNIQ-03)."""
    if request.method == "POST":
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
    return render(request, "accounts/riot_link.html", {"form": form})


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
    return render(request, "accounts/mypage.html", {"can_refresh": can_refresh(request.user)})
