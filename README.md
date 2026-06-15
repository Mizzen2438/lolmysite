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
| M3〜M7 | Riot 連携 / 募集 / 応募 / モデレーション / デプロイ | 未着手 |

## Discord OAuth の設定(M2)

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリを作成
2. OAuth2 のリダイレクト URL に `http://127.0.0.1:8000/accounts/discord/login/callback/` を追加
3. Client ID / Client Secret を `.env` の `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` に設定

新規ユーザーのフロー: Discord でログイン → 利用規約同意(F-SAFE-06)→ プロフィール設定 → マイページ。
作成から日の浅い Discord アカウント(既定 90 日未満)と凍結歴のある Discord ID はログインを拒否する(F-UNIQ-07 / F-UNIQ-04)。

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
