from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from recruitments.models import Recruitment

from . import services
from .models import Application


@login_required
@require_POST
def apply_view(request, pk):
    recruitment = get_object_or_404(Recruitment, pk=pk)
    desired_lane = request.POST.get("desired_lane", "")
    comment = request.POST.get("comment", "")
    try:
        services.apply(request.user, recruitment, desired_lane, comment)
    except services.ApplicationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "応募しました。募集主の承認をお待ちください。")
        warning = services.rank_band_warning(request.user, recruitment)
        if warning:
            messages.warning(request, warning)
    return redirect("recruitment_detail", pk=pk)


def _owner_action(request, application_pk, func, success_msg):
    application = get_object_or_404(
        Application.objects.select_related("recruitment"), pk=application_pk
    )
    if application.recruitment.owner_id != request.user.pk:
        messages.error(request, "権限がありません。")
        return redirect("recruitment_detail", pk=application.recruitment_id)
    try:
        func(application)
    except services.ApplicationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, success_msg)
    return redirect("recruitment_detail", pk=application.recruitment_id)


@login_required
@require_POST
def approve_view(request, pk):
    return _owner_action(request, pk, services.approve, "応募を承認しました。")


@login_required
@require_POST
def reject_view(request, pk):
    return _owner_action(request, pk, services.reject, "応募を見送りました。")


def _applicant_action(request, application_pk, func, success_msg):
    application = get_object_or_404(Application, pk=application_pk)
    if application.applicant_id != request.user.pk:
        messages.error(request, "権限がありません。")
        return redirect("recruitment_detail", pk=application.recruitment_id)
    try:
        func(application)
    except services.ApplicationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, success_msg)
    return redirect("recruitment_detail", pk=application.recruitment_id)


@login_required
@require_POST
def withdraw_view(request, pk):
    return _applicant_action(request, pk, services.withdraw, "応募を取り下げました。")


@login_required
@require_POST
def decline_view(request, pk):
    return _applicant_action(request, pk, services.decline, "参加を辞退しました。")
