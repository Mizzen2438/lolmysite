"""Application lifecycle: apply, approve, reject, withdraw, decline.

Approval is transactional with row locking so two simultaneous approvals
cannot oversubscribe a slot (ARCHITECTURE.md §5.4). Reaching zero open slots
auto-fills the recruitment and sends the Discord meetup notice (F-DSC-03).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from moderation.models import Block
from notifications.models import Notification, notify
from recruitments.models import Recruitment

from .models import Application


class ApplicationError(Exception):
    """User-facing error during the application flow."""


def check_can_apply(user, recruitment: Recruitment) -> None:
    """Raise ApplicationError if ``user`` may not apply (F-APP-01/05, §5.4)."""
    if not user.is_authenticated:
        raise ApplicationError("ログインが必要です。")
    if not user.is_riot_linked:
        raise ApplicationError("応募には Riot ID の連携が必要です。")
    if recruitment.status != Recruitment.Status.OPEN:
        raise ApplicationError("この募集は応募を受け付けていません。")
    if recruitment.is_hidden:
        raise ApplicationError("この募集は応募を受け付けていません。")
    if recruitment.owner_id == user.pk:
        raise ApplicationError("自分の募集には応募できません。")
    if Block.exists_between(user, recruitment.owner):
        raise ApplicationError("この募集には応募できません。")
    existing = recruitment.applications.filter(applicant=user).first()
    if existing and existing.is_active:
        raise ApplicationError("すでにこの募集に応募しています。")


def rank_band_warning(user, recruitment: Recruitment) -> str | None:
    """Return a warning if the applicant's rank is outside the band (F-SAFE-09)."""
    if recruitment.rank_min_idx is None and recruitment.rank_max_idx is None:
        return None
    tiers = recruitment.game.rank_tiers or []
    solo = user.rank_solo or ""
    tier_name = solo.split(" ")[0] if solo else ""
    if tier_name not in tiers:
        return None  # unranked / unknown: don't warn
    idx = tiers.index(tier_name)
    lo = recruitment.rank_min_idx if recruitment.rank_min_idx is not None else 0
    hi = recruitment.rank_max_idx if recruitment.rank_max_idx is not None else len(tiers) - 1
    if idx < lo or idx > hi:
        return "あなたのランクは募集の対象ランク帯から外れています。"
    return None


def apply(user, recruitment: Recruitment, desired_lane: str, comment: str = "") -> Application:
    check_can_apply(user, recruitment)
    open_lanes = set(recruitment.open_lanes())
    if desired_lane not in open_lanes and "FILL" not in open_lanes:
        raise ApplicationError("選択したレーンの空き枠がありません。")

    from recruitments.forms import contains_ng_word

    if comment and contains_ng_word(comment):
        raise ApplicationError("コメントに不適切な表現が含まれている可能性があります。")

    application, _ = Application.objects.update_or_create(
        recruitment=recruitment,
        applicant=user,
        defaults={
            "desired_lane": desired_lane,
            "comment": comment,
            "status": Application.Status.PENDING,
        },
    )
    notify(
        recruitment.owner,
        Notification.Type.APPLICATION_RECEIVED,
        message=f"{user} さんが「{recruitment.mode}」に応募しました。",
        recruitment_id=recruitment.pk,
    )
    return application


@transaction.atomic
def approve(application: Application) -> Application:
    """Approve an application, assign a slot, and auto-fill if complete."""
    recruitment = Recruitment.objects.select_for_update().get(pk=application.recruitment_id)
    if application.status != Application.Status.PENDING:
        raise ApplicationError("この応募は処理済みです。")

    lane = application.desired_lane
    slot = (
        recruitment.slots.select_for_update()
        .filter(member__isnull=True, lane=lane)
        .first()
        or recruitment.slots.select_for_update().filter(member__isnull=True, lane="FILL").first()
    )
    if slot is None:
        raise ApplicationError("空き枠がありません。")

    slot.member = application.applicant
    slot.save(update_fields=["member"])
    application.status = Application.Status.APPROVED
    application.save(update_fields=["status", "updated_at"])

    notify(
        application.applicant,
        Notification.Type.APPLICATION_APPROVED,
        message=f"「{recruitment.mode}」への参加が承認されました。",
        recruitment_id=recruitment.pk,
    )

    if not recruitment.slots.filter(member__isnull=True).exists():
        _fill_recruitment(recruitment)
    return application


def reject(application: Application) -> Application:
    if application.status != Application.Status.PENDING:
        raise ApplicationError("この応募は処理済みです。")
    application.status = Application.Status.REJECTED
    application.save(update_fields=["status", "updated_at"])
    notify(
        application.applicant,
        Notification.Type.APPLICATION_REJECTED,
        message=f"「{application.recruitment.mode}」への応募は見送られました。",
        recruitment_id=application.recruitment_id,
    )
    return application


def withdraw(application: Application) -> Application:
    if application.status != Application.Status.PENDING:
        raise ApplicationError("取り下げできる応募がありません。")
    application.status = Application.Status.WITHDRAWN
    application.save(update_fields=["status", "updated_at"])
    return application


@transaction.atomic
def decline(application: Application) -> Application:
    """An approved participant leaves; free their slot and reopen if needed."""
    if application.status != Application.Status.APPROVED:
        raise ApplicationError("辞退できる参加がありません。")
    recruitment = Recruitment.objects.select_for_update().get(pk=application.recruitment_id)
    recruitment.slots.filter(member=application.applicant).update(member=None)
    application.status = Application.Status.DECLINED
    application.save(update_fields=["status", "updated_at"])
    if recruitment.status == Recruitment.Status.FILLED:
        # Reopen for re-recruiting, unless the start time has already passed.
        if recruitment.start_at < timezone.now():
            recruitment.status = Recruitment.Status.EXPIRED
        else:
            recruitment.status = Recruitment.Status.OPEN
        recruitment.save(update_fields=["status"])
    notify(
        recruitment.owner,
        Notification.Type.PARTICIPANT_LEFT,
        message=f"{application.applicant} さんが「{recruitment.mode}」への参加を辞退しました。",
        recruitment_id=recruitment.pk,
    )
    return application


def _fill_recruitment(recruitment: Recruitment) -> None:
    recruitment.status = Recruitment.Status.FILLED
    recruitment.save(update_fields=["status"])
    # F-DSC-03: notify every participant with the meetup notice.
    member_ids = recruitment.slots.filter(member__isnull=False).values_list("member_id", flat=True)
    from accounts.models import User

    for member in User.objects.filter(pk__in=member_ids):
        notify(
            member,
            Notification.Type.RECRUITMENT_FILLED,
            message=f"「{recruitment.mode}」が成立しました。Discord に集合しましょう。",
            recruitment_id=recruitment.pk,
        )
