from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
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
        .filter(is_hidden=False)
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

    # F-SAFE-02: hide recruitments from users in a block relationship.
    if request.user.is_authenticated:
        from moderation.models import Block

        blocked_ids = set(
            Block.objects.filter(user=request.user).values_list("blocked_user_id", flat=True)
        ) | set(
            Block.objects.filter(blocked_user=request.user).values_list("user_id", flat=True)
        )
        if blocked_ids:
            qs = qs.exclude(owner_id__in=blocked_ids)

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
    from applications import services
    from applications.models import Application

    recruitment = get_object_or_404(
        Recruitment.objects.select_related("owner", "game").prefetch_related("slots__member"),
        pk=pk,
    )
    is_owner = recruitment.is_owner(request.user)
    # Hidden recruitments are visible only to the owner and staff (F-SAFE-07).
    if recruitment.is_hidden and not is_owner and not request.user.is_staff:
        raise Http404("この募集は公開されていません。")

    viewer_application = None
    apply_error = None
    pending_applications = None
    if request.user.is_authenticated:
        viewer_application = recruitment.applications.filter(applicant=request.user).first()
        if not is_owner:
            try:
                services.check_can_apply(request.user, recruitment)
            except services.ApplicationError as exc:
                apply_error = str(exc)
    if is_owner:
        pending_applications = (
            recruitment.applications.filter(status=Application.Status.PENDING)
            .select_related("applicant")
        )

    viewer_blocked_owner = False
    if request.user.is_authenticated and not is_owner:
        from moderation.models import Block

        viewer_blocked_owner = Block.objects.filter(
            user=request.user, blocked_user=recruitment.owner
        ).exists()

    return render(
        request,
        "recruitments/detail.html",
        {
            "recruitment": recruitment,
            "is_owner": is_owner,
            "can_view_invite": recruitment.can_view_invite(request.user),
            "open_lanes": sorted(set(recruitment.open_lanes())),
            "viewer_application": viewer_application,
            "apply_error": apply_error,
            "pending_applications": pending_applications,
            "viewer_blocked_owner": viewer_blocked_owner,
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
        _notify_participants(recruitment, "closed")
        messages.success(request, "募集を締め切りました。")
    return redirect("recruitment_detail", pk=pk)


@login_required
@require_POST
def recruitment_delete(request, pk):
    recruitment = get_object_or_404(Recruitment, pk=pk)
    if not recruitment.is_owner(request.user):
        messages.error(request, "権限がありません。")
        return redirect("recruitment_detail", pk=pk)
    _notify_participants(recruitment, "deleted")
    recruitment.delete()
    messages.success(request, "募集を削除しました。")
    return redirect("recruitment_list")


def _notify_participants(recruitment, kind):
    """Notify approved members (other than the owner) of a change (F-NTF-04)."""
    from notifications.models import Notification, notify

    type_map = {
        "closed": (Notification.Type.RECRUITMENT_CLOSED, "募集が締め切られました。"),
        "deleted": (Notification.Type.RECRUITMENT_DELETED, "参加予定の募集が削除されました。"),
    }
    ntype, message = type_map[kind]
    member_ids = (
        recruitment.slots.filter(member__isnull=False)
        .exclude(member_id=recruitment.owner_id)
        .values_list("member_id", flat=True)
    )
    from accounts.models import User

    for member in User.objects.filter(pk__in=set(member_ids)):
        rid = None if kind == "deleted" else recruitment.pk
        notify(member, ntype, message=f"「{recruitment.mode}」: {message}", recruitment_id=rid)
