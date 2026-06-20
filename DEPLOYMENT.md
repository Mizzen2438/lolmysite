# デプロイ手順(M7)

本番構成:

```
ユーザー → Cloudflare(DNS / SSL / CDN / WAF・無料)
                 ↓
        Render(Django Web)
            ├─ Supabase(PostgreSQL・東京)
            └─ Upstash(Redis・キャッシュ)

定期実行(expire_recruitments / refresh_ranks)は GitHub Actions
(.github/workflows/scheduled.yml)で代替する。
```

ドメイン: `neonq.online`(apex)と `www.neonq.online` の両方を使う。

## 1. 事前準備

| 項目 | 内容 |
|---|---|
| Discord アプリ | [Developer Portal](https://discord.com/developers/applications) で Client ID / Secret を取得。OAuth2 リダイレクト URL に `https://neonq.online/accounts/discord/login/callback/` と `https://www.neonq.online/accounts/discord/login/callback/` を登録 |
| Riot API キー | **Production API Key を申請**(N-14、`docs/RIOT_API_APPLICATION.md`)。開発中は Development Key で可 |
| Riot Sign On(RSO) | 本人所有確認(F-ACC-09)。**Production 承認後**に RSO Client を申請し、redirect URI に `https://neonq.online/onboarding/riot/rso/callback/` と `https://www.neonq.online/onboarding/riot/rso/callback/`、scope `openid offline_access` を登録。発行された `RSO_CLIENT_ID` / `RSO_CLIENT_SECRET` を設定する。**未設定の間は RSO 無効**(手動 Riot ID 入力にフォールバック) |
| Sentry | プロジェクトを作成し DSN を取得(N-12) |
| Supabase | プロジェクト作成(**Region: Northeast Asia (Tokyo)**)。DB の接続文字列を取得 |
| Upstash | Redis データベース作成。`rediss://` URL を取得 |
| Cloudflare | `neonq.online` をゾーンとして追加(レジストラのネームサーバーを Cloudflare に変更) |

## 2. Supabase(DB)

1. プロジェクトを **Tokyo** リージョンで作成。
2. Connect → Connection string から接続文字列を取得。
   - アプリ用 `DATABASE_URL` は **session プーラー(ポート 5432)** を使う。
   - **マイグレーションも 5432(session/直接)** に対して走らせる。transaction プーラー(6543)は一部 DDL で問題が出るため避ける。
3. この URL を Render の `DATABASE_URL`(`neonq-shared` グループ)に設定。

## 3. Upstash(Redis)

1. Redis データベースを作成(JP に近いリージョン)。
2. `rediss://default:<password>@<region>.upstash.io:6379` を Render の `CACHE_URL` に設定。

## 4. Render(Web サービス)

1. リポジトリを接続し **New → Blueprint** で `render.yaml` を読み込む(Web サービスが作成される。DB/Redis は外部なので Render では作らない)。
2. 環境変数グループ `neonq-shared` の `sync: false` を入力:
   - `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET`
   - `RIOT_API_KEY`(Production Key)
   - `SENTRY_DSN`
   - `DATABASE_URL`(Supabase)/ `CACHE_URL`(Upstash)
3. Web サービスに設定:
   - `DJANGO_ALLOWED_HOSTS` = `neonq.online,www.neonq.online,.onrender.com`
   - `DJANGO_CSRF_TRUSTED_ORIGINS` = `https://neonq.online,https://www.neonq.online,https://*.onrender.com`
   - `DJANGO_PREPEND_WWW` = `False`(www を正規ホストにしたい場合のみ `True`)
4. デプロイ。ビルドで `collectstatic`、起動時に `migrate`(無料枠は preDeploy 非対応のため startCommand 内で実行)→ `gunicorn`。まず Render の `<app>.onrender.com` で動作確認する。

> **定期実行(cron)について**: Render の cron は無料枠が無いため、`render.yaml` には含めていない。
> `expire_recruitments`(募集の自動期限切れ)と `refresh_ranks`(ランク日次更新)は、
> GitHub Actions のスケジュール(`.github/workflows/scheduled.yml`)で無料代替する。
> 同ワークフローは本番 DB に直接つなぐため、リポジトリ Secrets(Settings → Secrets and
> variables → Actions)に `DJANGO_SECRET_KEY` / `DATABASE_URL` / `CACHE_URL` /
> `RIOT_API_KEY`(任意で `RIOT_PLATFORM` / `RIOT_REGIONAL`)を設定する。手動実行は
> Actions タブの **Scheduled jobs → Run workflow** から(`expire` / `refresh` / `both`)。
> ローンチ初期はスケジュールが無くても致命的ではない(ランクは連携時/手動更新で取得、
> 期限切れは表示側でも考慮)。

## 5. Cloudflare + 独自ドメイン(neonq.online / www)

1. Render の Web サービス → Settings → Custom Domains に `neonq.online` と `www.neonq.online` を追加し、提示される接続先(`<app>.onrender.com` など)を控える。
2. Cloudflare の DNS に **CNAME** を 2 本作成(いずれも Proxied = オレンジ雲):
   - `www` → `<app>.onrender.com`
   - `neonq.online`(apex)→ `<app>.onrender.com`(Cloudflare は CNAME フラットニング対応)
3. Cloudflare → SSL/TLS の暗号化モードを **Full (Strict)** にする(Render は正規証明書を持つため)。
4. **正規化リダイレクト**(どちらか一方に統一して SEO 重複を防ぐ):
   - apex を正規にする(推奨・URL が短い): Cloudflare の Redirect Rule で `www.neonq.online/*` → `https://neonq.online/$1`(301)。
   - www を正規にする場合: Render に `DJANGO_PREPEND_WWW=True` を設定(apex→www を Django が 301)。
5. 反映後、`https://neonq.online` と `https://www.neonq.online` の両方で表示されること、片方がもう片方へ 301 することを確認。

> 注意: Cloudflare のプロキシ配下では `X-Forwarded-Proto` が渡る。Django は `SECURE_PROXY_SSL_HEADER` 設定済みなのでリダイレクトループは起きない。SSL モードを Flexible にすると無限リダイレクトになるため必ず Full (Strict)。

## 6. デプロイ後の初期設定

初回デプロイ後に、ゲームマスタ初期データと運営アカウントを本番 DB に投入する。

> **無料枠には Render Shell が無い**ため、`render.yaml` の cron 同様、GitHub Actions の
> ホストランナーから本番 DB(Supabase)へ直接つないで実行する
> (`.github/workflows/initial-setup.yml`、手動実行専用)。

1. リポジトリ Secrets(Settings → Secrets and variables → Actions)を用意:
   - `DJANGO_SECRET_KEY` / `DATABASE_URL` … scheduled.yml と共用(設定済みのはず)
   - `DJANGO_SUPERUSER_PASSWORD` … **このワークフロー用に新規追加**(運営アカウントのパスワード)
2. Actions タブ → **Initial setup → Run workflow** を実行:
   - `task` = `both`(初回。`loaddata` / `superuser` で個別実行も可)
   - `discord_id` = **運営者本人の Discord 数値ID**(Discord の開発者モードを有効化 →
     自分を右クリック →「ユーザーIDをコピー」)。サイト本体は Discord OAuth ログインのため、
     ここで実アカウントの ID を入れると同一アカウントとして `/admin/` とサイトの両方を使える。

実行内容(= 旧 Render Shell 手順と同等):

```bash
python manage.py loaddata league_of_legends   # ゲームマスタ初期データ(games.Game pk=1)
python manage.py createsuperuser               # 運営アカウント(Discord ID + パスワード)
```

> **冪等性**: `loaddata` は pk 固定のため再実行で上書き(初回のみで十分)。`superuser` は
> 再実行すると既存ユーザーをスーパーユーザー化しパスワードを再設定する(パスワード再設定にも使える)。
>
> 別法: ローカルに開発環境があれば、本番の Session pooler URL を使って
> `DATABASE_URL='<本番URL>' python manage.py loaddata league_of_legends` /
> `… createsuperuser` を手元から実行してもよい。

## 7. 動作確認チェックリスト

- [ ] `https://neonq.online/healthz` が `{"status": "ok"}` を返す
- [ ] `https://www.neonq.online` → `https://neonq.online`(または逆)に 301
- [ ] HTTP は HTTPS に転送される
- [ ] 静的ファイルがハッシュ付き URL で配信される(`DJANGO_MANIFEST_STATIC=True`)
- [ ] Discord でログイン →(規約同意 → プロフィール → Riot 連携)が通る
- [ ] Riot 連携でランクが自動取得・表示される
- [ ] 募集作成 → 別ユーザーで応募 → 承認 → 成立 → 集合案内通知 → 招待リンク表示
- [ ] `/admin/` で通報確認・凍結・募集非公開化ができる
- [ ] 定期実行(`expire_recruitments`・`refresh_ranks`)が成功(GitHub Actions の Scheduled jobs ログ)
- [ ] Sentry にイベントが届く
- [ ] Supabase が無操作で pause していない(ローンチ後はトラフィックで回避)

## 8. 運用メモ

- 設定は環境変数駆動。シークレットはリポジトリにコミットしない(N-04)。
- 本番は `DEBUG=False` により HTTPS 強制・HSTS・セキュアクッキー(N-05)。
- Riot API レスポンスは Upstash にキャッシュ(N-13)。
- **無料枠の注意**: Render 無料 Web はアイドルでスリープ(コールドスタート)、Supabase 無料は無操作で pause。ローンチ時は Render Web を最小有料にし、Supabase はトラフィックで起こし続けるのが安全。
- バックアップは Supabase の自動バックアップを利用。
