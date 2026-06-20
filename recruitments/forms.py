from __future__ import annotations

from django import forms
from django.conf import settings
from django.utils import timezone

from games.models import Game

from .models import Recruitment, RecruitmentSlot

DURATION_CHOICES = [
    ("1時間", "1時間"),
    ("2〜3時間", "2〜3時間"),
    ("3時間以上", "3時間以上"),
    ("決めない", "決めない"),
]
VC_TOOL_CHOICES = [
    ("Discord VC(必須)", "Discord VC(必須)"),
    ("Discord VC(聞き専OK)", "Discord VC(聞き専OK)"),
    ("なし(ゲーム内チャットのみ)", "なし(ゲーム内チャットのみ)"),
]


def _get_lol_game() -> Game | None:
    return Game.objects.filter(slug="league-of-legends").first()


def contains_ng_word(text: str) -> bool:
    lowered = text.lower()
    return any(w and w.lower() in lowered for w in settings.NG_WORDS)


class RecruitmentBaseForm(forms.ModelForm):
    """Shared fields and rank-band handling (F-REC-02)."""

    rank_min = forms.ChoiceField(label="対象ランク下限", required=False)
    rank_max = forms.ChoiceField(label="対象ランク上限", required=False)
    tags = forms.MultipleChoiceField(
        label="雰囲気タグ",
        required=False,
        choices=Recruitment.TAG_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Recruitment
        fields = ["mode", "start_at", "duration_label", "vc_tool", "tags", "comment", "discord_invite_url"]
        widgets = {
            "start_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "comment": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = _get_lol_game()
        tiers = self.game.rank_tiers if self.game else []
        modes = self.game.modes if self.game else []
        self.fields["mode"] = forms.ChoiceField(
            label="ゲームモード", choices=[(m, m) for m in modes]
        )
        rank_choices = [("", "指定なし")] + [(str(i), t) for i, t in enumerate(tiers)]
        self.fields["rank_min"].choices = rank_choices
        self.fields["rank_max"].choices = rank_choices
        self.fields["duration_label"] = forms.ChoiceField(
            label="想定プレイ時間", choices=DURATION_CHOICES, required=False
        )
        self.fields["vc_tool"] = forms.ChoiceField(
            label="ボイスチャット", choices=VC_TOOL_CHOICES, required=False
        )
        # 集合導線(F-DSC-01/03)。Bot 連携が有効なら成立時に専用 VC を自動発行
        # するため任意。無効な環境では唯一の導線になるため必須化する。
        if settings.DISCORD_BOT_ENABLED:
            self.fields["discord_invite_url"].required = False
            self.fields["discord_invite_url"].label = "Discord 招待リンク(任意)"
            self.fields["discord_invite_url"].help_text = (
                "成立時に参加者専用の Discord VC を自動で発行します。"
                "常設サーバーへ案内したい場合のみ、招待リンクを入力してください。"
            )
        else:
            self.fields["discord_invite_url"].required = True
            self.fields["discord_invite_url"].help_text = (
                "成立後、承認した参加者にのみ表示されます。"
                "Discord サーバー招待リンク(例: https://discord.gg/xxxx)または VC の URL を入力してください。"
            )
        self.fields["start_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        # Pre-fill rank selects when editing.
        if self.instance and self.instance.pk:
            if self.instance.rank_min_idx is not None:
                self.fields["rank_min"].initial = str(self.instance.rank_min_idx)
            if self.instance.rank_max_idx is not None:
                self.fields["rank_max"].initial = str(self.instance.rank_max_idx)

    def clean_start_at(self):
        start_at = self.cleaned_data["start_at"]
        if start_at and start_at < timezone.now():
            raise forms.ValidationError("開始予定時刻は未来の時刻にしてください。")
        return start_at

    def clean_comment(self):
        comment = self.cleaned_data.get("comment", "")
        if comment and contains_ng_word(comment):
            raise forms.ValidationError("不適切な表現が含まれている可能性があります。")
        return comment

    def clean(self):
        cleaned = super().clean()
        rmin = cleaned.get("rank_min")
        rmax = cleaned.get("rank_max")
        imin = int(rmin) if rmin not in (None, "") else None
        imax = int(rmax) if rmax not in (None, "") else None
        if imin is not None and imax is not None and imin > imax:
            raise forms.ValidationError("ランク帯の下限が上限を上回っています。")
        cleaned["rank_min_idx"] = imin
        cleaned["rank_max_idx"] = imax
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.rank_min_idx = self.cleaned_data.get("rank_min_idx")
        obj.rank_max_idx = self.cleaned_data.get("rank_max_idx")
        obj.vc_required = "必須" in (obj.vc_tool or "")
        if self.game:
            obj.game = self.game
        if commit:
            obj.save()
        return obj


class RecruitmentCreateForm(RecruitmentBaseForm):
    """Adds slot-building fields used only at creation time (F-REC-01)."""

    my_lane = forms.ChoiceField(label="自分の担当レーン")
    wanted_lanes = forms.MultipleChoiceField(
        label="募集するレーン", required=False, widget=forms.CheckboxSelectMultiple
    )
    additional_slots = forms.IntegerField(
        label="追加募集枠(FILL)", required=False, min_value=0, max_value=4, initial=0,
        help_text="ARAM など役割を問わない枠を追加します。",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lanes = self.game.lanes if self.game else []
        self.fields["my_lane"].choices = [(lane, lane) for lane in lanes]
        self.fields["wanted_lanes"].choices = [(lane, lane) for lane in lanes]

    def clean(self):
        cleaned = super().clean()
        wanted = cleaned.get("wanted_lanes") or []
        additional = cleaned.get("additional_slots") or 0
        if not wanted and not additional:
            raise forms.ValidationError("募集するレーンか追加募集枠を 1 つ以上指定してください。")
        return cleaned

    def create(self, owner) -> Recruitment:
        obj = self.save(commit=False)
        obj.owner = owner
        obj.save()
        # Owner's own filled slot, then the open slots they want to fill.
        RecruitmentSlot.objects.create(recruitment=obj, lane=self.cleaned_data["my_lane"], member=owner)
        for lane in self.cleaned_data.get("wanted_lanes") or []:
            RecruitmentSlot.objects.create(recruitment=obj, lane=lane)
        for _ in range(self.cleaned_data.get("additional_slots") or 0):
            RecruitmentSlot.objects.create(recruitment=obj, lane="FILL")
        return obj


class RecruitmentEditForm(RecruitmentBaseForm):
    """Edit recruitment fields without restructuring existing slots (F-REC-04)."""
