# LoL MySite

League of Legends のメンバー募集・応募の専門サービス。

- 要件定義書: [REQUIREMENTS.md](./REQUIREMENTS.md)
- 基本設計書: [ARCHITECTURE.md](./ARCHITECTURE.md)
- 画面プロトタイプ(静的 HTML): [prototype/](./prototype/)

技術スタック: Python 3.12 / Django 5.1 / PostgreSQL 16 / Redis(後続マイルストーン)。

## 実装状況

| マイルストーン | 内容 | 状況 |
|---|---|---|
| M1 | プロジェクト雛形・ゲームマスタ・カスタムユーザー・CI | ✅ 完了 |
| M2 | Discord OAuth ログイン・一意性チェック・規約同意・プロフィール設定 | ✅ 完了 |
| M3 | Riot 連携(実在確認・ランク取得・キャッシュ・手動/定期更新) | ✅ 完了 |
| M4 | 募集 CRUD・一覧フィルタ・自動期限切れ | ✅ 完了 |
| M5 | 応募・承認・成立・Discord 集合案内・サイト内通知 | ✅ 完了 |
| M6〜M7 | モデレーション / デプロイ | 未着手 |

## Discord OAuth の設定(M2)

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリを作成
2. OAuth2 のリダイレクト URL に `http://127.0.0.1:8000/accounts/discord/login/callback/` を追加
3. Client ID / Client Secret を `.env` の `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` に設定

新規ユーザーのフロー: Discord でログイン → 利用規約同意(F-SAFE-06)→ プロフィール設定 → Riot ID 連携 → マイページ。
作成から日の浅い Discord アカウント(既定 90 日未満)と凍結歴のある Discord ID はログインを拒否する(F-UNIQ-07 / F-UNIQ-04)。

## Riot 連携(M3)

- `RIOT_API_KEY` を `.env` に設定(開発は Development Key、本番は Production Key を申請 = N-14)。
- ランクは Riot API から自動取得され、自己申告はできない(F-ACC-06)。ソロ/フレックスをマイページに表示。
- 応答は Django キャッシュ(本番は Redis = `CACHE_URL`)に既定 24h 保存(N-13)。手動更新は既定 10 分のクールダウン付き。
- 定期更新は管理コマンドで実行する(F-ACC-08):

  ```bash
  python manage.py refresh_ranks            # 直近7日ログインかつ連携済みユーザーを更新
  python manage.py refresh_ranks --active-days 14
  ```

  本番では Render Cron Job / Celery Beat / system cron で日次スケジュールする。

## 募集(M4)

- 募集の作成・編集・締切・削除(締切/削除/編集は募集主のみ = F-REC-04)。
- 作成時にレーン枠(自分の担当 + 募集レーン + 追加 FILL 枠)を生成。
- 一覧はモード・ランク帯・空きレーン・タグ・募集中のみで絞り込み(F-SRCH-02)。
- Discord 招待リンクは一覧クエリから除外し、募集主・参加者のみに表示(F-DSC-02 / N-06)。
- 開始時刻を過ぎた募集中の募集を期限切れにする(F-REC-05、毎分スケジュール推奨):

  ```bash
  python manage.py expire_recruitments
  ```

## 応募・通知(M5)

- 応募条件: ログイン + Riot 連携 + 募集中 + 自分の募集でない + ブロックなし + 重複なし(F-APP-01/05、§5.4)。
- 承認はトランザクション + 行ロックで枠を割当(同時承認の競合を防止)。空き枠が 0 になると自動で成立し、参加者全員へ Discord 集合案内を通知(F-DSC-03)。
- 応募者は取り下げ、参加者は辞退(辞退すると枠が空き、成立済みなら募集中に戻る)。
- 募集主の応募管理(承認/見送り)は募集詳細ページから。
- サイト内通知(F-NTF)はヘッダーの「通知」に未読バッジ付きで表示。ランク帯から外れた応募には警告を表示(F-SAFE-09)。

## ローカル開発(SQLite クイックスタート)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # DATABASE_URL は空のまま = SQLite
python manage.py migrate
python manage.py loaddata league_of_legends   # ゲームマスタ初期データ
python manage.py createsuperuser               # 管理者(Discord ID + パスワード)
python manage.py runserver
```

管理画面: http://127.0.0.1:8000/admin/ — 作成した superuser でログイン可能。

> 一般ユーザーは Discord OAuth でログインする想定(M2 で実装)。superuser のみ
> パスワードを持ち、Django Admin による運営操作(通報対応・凍結 = F-SAFE-07)に使う。

## Docker Compose(PostgreSQL)

```bash
docker compose up --build
docker compose exec web python manage.py loaddata league_of_legends
docker compose exec web python manage.py createsuperuser
```

## テスト・Lint

```bash
python manage.py test
ruff check .
python manage.py makemigrations --check --dry-run   # マイグレーション差分チェック
```

GitHub Actions(`.github/workflows/ci.yml`)で PostgreSQL サービス上の
テスト・lint・マイグレーション差分チェックを自動実行する。
