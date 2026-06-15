# デプロイ手順(M7)

Render の Blueprint(`render.yaml`)を前提とした手順。Railway / Fly.io でも
`Procfile`・環境変数・cron 相当を用意すれば同様に動く。

## 1. 事前準備

| 項目 | 内容 |
|---|---|
| Discord アプリ | [Developer Portal](https://discord.com/developers/applications) で Client ID / Secret を取得。OAuth2 リダイレクト URL に `https://<本番ドメイン>/accounts/discord/login/callback/` を登録 |
| Riot API キー | **Production API Key を申請**(N-14)。承認に日数がかかるため早めに。開発中は Development Key で可 |
| Sentry | プロジェクトを作成し DSN を取得(N-12) |

## 2. Render へのデプロイ

1. リポジトリを Render に接続し、**New → Blueprint** で `render.yaml` を読み込む。
   - Web サービス / PostgreSQL / Redis / cron 2 本(`expire_recruitments` 毎分・`refresh_ranks` 日次)が作成される。
2. 環境変数グループ `lolmysite-shared` の `sync: false` 項目を入力:
   - `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET`
   - `RIOT_API_KEY`(Production Key)
   - `SENTRY_DSN`
3. Web サービスに以下を設定:
   - `DJANGO_ALLOWED_HOSTS` = 本番ドメイン(例: `lolmysite.onrender.com`)
   - `DJANGO_CSRF_TRUSTED_ORIGINS` = `https://lolmysite.onrender.com`
4. デプロイを実行。ビルドで `collectstatic`、リリース前に `migrate` が走る。

## 3. デプロイ後の初期設定

```bash
# Render の Shell から
python manage.py loaddata league_of_legends   # ゲームマスタ初期データ
python manage.py createsuperuser               # 運営アカウント(Discord ID + パスワード)
```

## 4. 動作確認チェックリスト

- [ ] `https://<ドメイン>/healthz` が `{"status": "ok"}` を返す
- [ ] トップ・募集一覧が表示される(HTTP は HTTPS に 301 リダイレクト)
- [ ] 静的ファイルがハッシュ付き URL で配信される(`DJANGO_MANIFEST_STATIC=True`)
- [ ] Discord でログイン →(規約同意 → プロフィール → Riot 連携)が通る
- [ ] Riot 連携でランクが自動取得・表示される
- [ ] 募集作成 → 別ユーザーで応募 → 承認 → 成立 → 集合案内通知 → 招待リンク表示
- [ ] `/admin/` で通報確認・凍結・募集非公開化ができる
- [ ] cron: `expire_recruitments`・`refresh_ranks` が成功している(Render の cron ログ)
- [ ] Sentry にイベントが届く(任意のエラーで確認)

## 5. 運用メモ

- 設定は環境変数駆動(`config/settings.py`)。シークレットはリポジトリにコミットしない(N-04)。
- 本番では `DEBUG=False` により HTTPS 強制・HSTS・セキュアクッキーが有効(N-05)。
- Riot API はレートリミット遵守のためレスポンスを Redis にキャッシュ(N-13)。
- バックアップはマネージド PostgreSQL の自動バックアップを利用。
