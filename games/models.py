from django.db import models


class Game(models.Model):
    """Master data for a supported game title (N-11).

    Game-specific values (modes, lanes/roles, rank tiers) are stored here as
    JSON lists rather than hard-coded, so a new title can be added by creating
    a row instead of changing code. ``rank_tiers`` is ordered from lowest to
    highest; recruitments reference a tier by its index in this list.
    """

    name = models.CharField("名称", max_length=100)
    slug = models.SlugField("スラッグ", max_length=100, unique=True)
    modes = models.JSONField(
        "ゲームモード一覧",
        default=list,
        help_text='例: ["ランク(フレックス)", "ARAM"]',
    )
    lanes = models.JSONField(
        "レーン/ロール一覧",
        default=list,
        help_text='例: ["TOP", "JG", "MID", "ADC", "SUP", "FILL"]',
    )
    rank_tiers = models.JSONField(
        "ランク帯一覧(低→高の順)",
        default=list,
        help_text='例: ["アイアン", "ブロンズ", ..., "チャレンジャー"]',
    )
    is_active = models.BooleanField("有効", default=True)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)

    class Meta:
        verbose_name = "ゲーム"
        verbose_name_plural = "ゲーム"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
