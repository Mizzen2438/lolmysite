from __future__ import annotations

from django import forms

from games.models import Game

from .models import User

DEFAULT_LANES = ["TOP", "JG", "MID", "ADC", "SUP", "FILL"]


def _lane_choices() -> list[tuple[str, str]]:
    """Lane options sourced from the LoL game master (N-11), with a fallback."""
    game = Game.objects.filter(slug="league-of-legends").first()
    lanes = game.lanes if game and game.lanes else DEFAULT_LANES
    return [(lane, lane) for lane in lanes]


class ProfileForm(forms.ModelForm):
    lanes = forms.MultipleChoiceField(
        label="得意レーン",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = User
        fields = ["lanes", "play_hours", "vc_style", "bio"]
        widgets = {
            "play_hours": forms.TextInput(
                attrs={"placeholder": "例: 平日 21時〜24時 / 休日 昼〜"}
            ),
            "bio": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lanes"].choices = _lane_choices()


class RiotLinkForm(forms.Form):
    game_name = forms.CharField(
        label="ゲーム名", max_length=64,
        widget=forms.TextInput(attrs={"placeholder": "例: Hikari"}),
    )
    tagline = forms.CharField(
        label="タグライン", max_length=16,
        widget=forms.TextInput(attrs={"placeholder": "例: JP1"}),
    )
