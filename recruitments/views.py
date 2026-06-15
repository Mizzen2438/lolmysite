from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from games.models import Game

from .forms import RecruitmentCreateForm, RecruitmentEditForm
from .models import Recruitment


def recruitment_list(request):
    """Public list with filters mirroring the prototype (F-SRCH-01/02)."""
    game = Game.objects.filter(slug="league-of-legends").first()
    tiers = game.rank_tiers if game else []

    # Defer the invite URL so it never reaches the list (F-DSC-02, N-06).
    qs = (
        Recruitment.objects.defer("discord_invite_url")
        .select_related("owner", "game")
        .prefetch_related("slots")
    )

    mode = request.GET.get("mode", "")
    rank = request.GET.get("rank", "")
    lane = request.GET.get("lane", "")
    tag = request.GET.get("tag", "")
    open_only = request.GET.get("open", "1") == "1"

    if open_only:
        qs = qs.filter(status=Recruitment.Status.OPEN)
    if mode:
        qs = qs.filter(mode=mode)
    if lane:
        qs = qs.filter(
            slots__member__isnull=True, slots__lane__in=[lane, "FILL"]
        ).distinct()
    if tag:
        qs = qs.filter(tags__contains=[tag])
    if rank and rank.isdigit():
        idx = int(rank)
        qs = qs.filter(
            Q(rank_min_idx__lte=idx) | Q(rank_min_idx__isnull=True),
            Q(rank_max_idx__gte=idx) | Q(rank_max_idx__isnull=True),
        )

    context = {
        "recruitments": qs,
        "modes": game.modes if game else [],
        "tiers": list(enumerate(tiers)),
        "lanes": game.lanes if game else [],
        "tags": Recruitment.TAG_CHOICES,
        "selected": {"mode": mode, "rank": rank, "lane": lane, "tag": tag, "open": open_only},
    }
    return render(request, "recruitments/list.html", context)


def recruitment_detail(request, pk):
    recruitment = get_object_or_404(
        Recruitment.objects.select_related("owner", "game").prefetch_related("slots__member"),
        pk=pk,
    )
    return render(
        request,
        "recruitments/detail.html",
        {
            "recruitment": recruitment,
            "is_owner": recruitment.is_owner(request.user),
            "can_view_invite": recruitment.can_view_invite(request.user),
        },
    )


@login_required
def recruitment_create(request):
    if request.method == "POST":
        form = RecruitmentCreateForm(request.POST)
        if form.is_valid():
            recruitment = form.create(owner=request.user)
            messages.success(request, "募集を公開しました。")
            return redirect("recruitment_detail", pk=recruitment.pk)
    else:
        form = RecruitmentCreateForm()
    return render(request, "recruitments/form.html", {"form": form, "creating": True})


@login_required
def recruitment_edit(request, pk):
    recruitment = get_object_or_404(Recruitment, pk=pk)
    if not recruitment.is_owner(request.user):
        messages.error(request, "この募集を編集する権限がありません。")
        return redirect("recruitment_detail", pk=pk)
    if request.method == "POST":
        form = RecruitmentEditForm(request.POST, instance=recruitment)
        if form.is_valid():
            form.save()
            messages.success(request, "募集を更新しました。")
            return redirect("recruitment_detail", pk=pk)
    else:
        form = RecruitmentEditForm(instance=recruitment)
    return render(request, "recruitments/form.html", {"form": form, "creating": False})


@login_required
@require_POST
def recruitment_close(request, pk):
    recruitment = get_object_or_404(Recruitment, pk=pk)
    if not recruitment.is_owner(request.user):
        messages.error(request, "権限がありません。")
        return redirect("recruitment_detail", pk=pk)
    if recruitment.status == Recruitment.Status.OPEN:
        recruitment.status = Recruitment.Status.CLOSED
        recruitment.save(update_fields=["status"])
        messages.success(request, "募集を締め切りました。")
    return redirect("recruitment_detail", pk=pk)


@login_required
@require_POST
def recruitment_delete(request, pk):
    recruitment = get_object_or_404(Recruitment, pk=pk)
    if not recruitment.is_owner(request.user):
        messages.error(request, "権限がありません。")
        return redirect("recruitment_detail", pk=pk)
    recruitment.delete()
    messages.success(request, "募集を削除しました。")
    return redirect("recruitment_list")
