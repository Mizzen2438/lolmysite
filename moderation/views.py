from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from recruitments.models import Recruitment

from .forms import ReportForm
from .models import Block, Report

User = get_user_model()


@login_required
def report_create(request, target_type, target_id):
    """Report a user or a recruitment (F-SAFE-01)."""
    if target_type not in (Report.TargetType.USER, Report.TargetType.RECRUITMENT):
        messages.error(request, "不正な通報対象です。")
        return redirect("recruitment_list")

    # Resolve target for display and to prevent self-reporting.
    if target_type == Report.TargetType.USER:
        target = get_object_or_404(User, pk=target_id)
        label = str(target)
        if target.pk == request.user.pk:
            messages.error(request, "自分自身は通報できません。")
            return redirect("mypage")
    else:
        target = get_object_or_404(Recruitment, pk=target_id)
        label = f"募集: {target.mode}"

    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.target_type = target_type
            report.target_id = target_id
            report.save()
            messages.success(request, "通報を受け付けました。運営が内容を確認します。")
            if target_type == Report.TargetType.RECRUITMENT:
                return redirect("recruitment_detail", pk=target_id)
            return redirect("recruitment_list")
    else:
        form = ReportForm()
    return render(
        request,
        "moderation/report_form.html",
        {"form": form, "label": label},
    )


@login_required
@require_POST
def block_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "自分自身はブロックできません。")
        return redirect("mypage")
    Block.objects.get_or_create(user=request.user, blocked_user=target)
    messages.success(request, f"{target} さんをブロックしました。")
    return redirect(request.POST.get("next") or "mypage")


@login_required
@require_POST
def unblock_user(request, user_id):
    Block.objects.filter(user=request.user, blocked_user_id=user_id).delete()
    messages.success(request, "ブロックを解除しました。")
    return redirect(request.POST.get("next") or "blocked_list")


@login_required
def blocked_list(request):
    blocks = request.user.blocking.select_related("blocked_user").all()
    return render(request, "moderation/blocked_list.html", {"blocks": blocks})
