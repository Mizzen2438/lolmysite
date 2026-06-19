# NEONQ

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
| M6 | 通報・ブロック・運営フロー(Admin) | ✅ 完了 |
| M7 | 本番デプロイ設定・Sentry・cron | ✅ 完了 |

MVP(フェーズ 1)の全マイルストーン M1〜M7 が完了。本番デプロイ手順は [DEPLOYMENT.md](./DEPLOYMENT.md) を参照。

## ローカルデモモード(Discord / Riot の認証情報なしで試す)

Discord OAuth や Riot API キーを用意しなくても、サンプルデータ + パスワードレスの
開発用ログインで全フロー(募集作成 → 応募 → 承認 → 成立 → 集合案内)を試せる。
**`DEBUG=True` のときのみ有効**(本番では `/dev-login/` は 404)。

```bash
python manage.py migrate
python manage.py seed_demo      # デモユーザー4名・募集3件・応募1件を投入(冪等)
python manage.py runserver
```

ブラウザで `http://127.0.0.1:8000/login/` →「ローカルデモログイン(Discord 不要)」、
または直接 `http://127.0.0.1:8000/dev-login/` から好きなデモユーザーでログインする。
「デモ太郎」でログインすると、自分の募集に届いた「デモ次郎」の応募を承認 → 成立 →
Discord 集合案内まで確認できる。

> 本番で誤って有効化しないこと。`DEV_LOGIN_ENABLED` は既定で `DEBUG` に従う。

## Discord OAuth の設定(M2)

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリを作成
2. OAuth2 のリダイレクト URL に `http://127.0.0.1:8000/accounts/discord/login/callback/` を追加
3. Client ID / Client Secret を `.env` の `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` に設定

新規ユーザーのフロー: Discord でログイン → 利用規約同意(F-SAFE-06)→ プロフィール設定 → Riot ID 連携 → マイページ。
作成から日の浅い Discord アカウント(既定 90 日未満)と凍結歴のある Discord ID はログインを拒否する(F-UNIQ-07 / F-UNIQ-04)。

## Riot 連携(M3)

- `RIOT_API_KEY` を `.env` に設定(開発は Development Key、本番は Production Key を申請 = N-14)。申請準備は [docs/RIOT_API_APPLICATION.md](./docs/RIOT_API_APPLICATION.md)。
- 公開の利用規約 `/terms/`・プライバシーポリシー `/privacy/`、および Riot 法的免責表記(全ページフッター)を用意済み(Riot 審査の前提)。
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

## 通報・ブロック・運営フロー(M6)

- ユーザー/募集を通報できる(理由選択 + 自由記述、理由に「サブ垢・スマーフの疑い」を含む = F-SAFE-01)。
- ユーザーをブロックでき、ブロック関係にある相手の募集は一覧から除外され、相互に応募できない(F-SAFE-02)。マイページの「ブロック管理」で解除。
- 運営は Django Admin で対応する(F-SAFE-07):
  - 通報一覧の確認と状態変更(確認中/対応済み/却下)。
  - ユーザーの警告・凍結・凍結解除(凍結は `SanctionRecord` を Discord ID 単位で記録し、再登録を拒否 = F-UNIQ-04)。
  - 募集の非公開化/公開(非公開の募集は一覧・詳細から隠れる)。
- 募集コメント・応募コメントに NG ワードフィルタを適用(F-SAFE-08)。

## 本番デプロイ(M7)

- 構成: **Cloudflare(前段)+ Render(Django/cron)+ Supabase(PostgreSQL)+ Upstash(Redis)**。
- Render Blueprint(`render.yaml`): Web + cron 2 本を定義(DB/Redis は外部マネージドを `DATABASE_URL`/`CACHE_URL` で接続)。
- ドメイン `neonq.online` と `www.neonq.online` の両対応(正規化リダイレクトは Cloudflare か `DJANGO_PREPEND_WWW`)。
- `Procfile`(release で migrate)・`runtime.txt`(Python 3.12)で Heroku 系にも対応。
- 本番は `DEBUG=False` で HTTPS 強制・HSTS・セキュアクッキー(N-05)、静的ファイルは WhiteNoise の manifest ストレージ。
- Sentry でエラー監視(`SENTRY_DSN` = N-12)。`python manage.py check --deploy` がクリーン。
- 手順とチェックリストは [DEPLOYMENT.md](./DEPLOYMENT.md)。Riot は Production API Key を申請する(N-14)。

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
