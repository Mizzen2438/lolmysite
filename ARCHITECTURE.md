# 基本設計書 — ゲーム仲間募集サービス(LoL MySite)

- 版数: 1.0(ドラフト)
- 作成日: 2026-06-12
- 前提: [REQUIREMENTS.md](./REQUIREMENTS.md) v1.1 のフェーズ 1(MVP)を対象とする

---

## 1. 技術選定

### 1.1 採用スタック

| 領域 | 採用技術 | 備考 |
|---|---|---|
| 言語 | Python 3.12+ | |
| Web フレームワーク | **Django 5.x** | フルスタック MVC。テンプレートでサーバーサイドレンダリング |
| 認証 | **django-allauth**(Discord プロバイダ) | Discord OAuth2 ログイン(F-ACC-01) |
| DB | **PostgreSQL 16** | 本番。ローカル開発は Docker Compose で同一バージョン |
| キャッシュ | Redis | Riot API レスポンスのキャッシュ(N-13)、セッション |
| 非同期・定期処理 | **Celery + Celery Beat**(ブローカー: Redis) | ランク定期更新、募集の自動期限切れ、通知 |
| HTTP クライアント | httpx | Riot API 呼び出し |
| フロントエンド | Django テンプレート + 素の JS(既存プロトタイプの CSS/JS を移植) | MVP では SPA を採用しない |
| エラー監視 | Sentry(無料枠) | N-12 |
| デプロイ | Render / Railway / Fly.io のいずれか(後述) | |

### 1.2 Django を採用する理由(FastAPI との比較)

| 観点 | Django | FastAPI |
|---|---|---|
| 管理画面(F-SAFE-07: 通報対応・凍結) | **Django Admin が標準装備**。モデル定義だけで運営画面が手に入る | 自作が必要 |
| 認証・セッション・CSRF | 標準装備 + allauth で Discord OAuth が設定のみ | 自作または外部ライブラリの組み合わせ |
| ORM・マイグレーション | 標準装備 | SQLAlchemy + Alembic を別途構成 |
| 向いている形 | サーバーレンダリングの CRUD アプリ(本サービスはこれ) | API 専業・SPA/モバイルのバックエンド |

本サービスの MVP は「フォームと一覧が中心の CRUD + 運営管理画面」であり、Django の標準機能がそのまま要件を満たす。リアルタイム性の高い機能(チャット等)はスコープ外のため、FastAPI の非同期性能は不要。**フェーズ 3 でスマホアプリ化する場合は、Django REST Framework で API を追加する拡張余地を残す。**

---

## 2. システム構成

```
                        ┌──────────────────────────────┐
                        │  ホスティング(Render 等)        │
  ユーザー(ブラウザ)──▶│  Django(gunicorn)             │
                        │   ├─ Web(テンプレート描画)      │
                        │   ├─ Django Admin(運営用)      │
                        │   └─ Celery Worker / Beat      │
                        └────┬──────────┬───────────────┘
                             │          │
                      PostgreSQL      Redis(キャッシュ/ブローカー)
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
      Discord API                     Riot Games API
      ・OAuth2(ログイン)             ・Account-V1(Riot ID→PUUID)
      ・(将来)Bot 通知               ・Summoner-V4 / League-V4(ランク)
```

- 単一リージョン・単一インスタンスで開始(N-02 の同時 500 ユーザーは Django + gunicorn 1〜2 台で十分)
- 静的ファイルは WhiteNoise で配信(MVP では CDN 不要)

---

## 3. Django アプリケーション構成

| アプリ | 責務 | 主要モデル |
|---|---|---|
| `accounts` | Discord OAuth、プロフィール、Riot 連携、一意性チェック(F-ACC, F-UNIQ) | User, SanctionRecord |
| `games` | ゲームマスタ(レーン・モード・ランク帯の定義)(N-11) | Game |
| `recruitments` | 募集の CRUD・検索・ライフサイクル(F-REC, F-SRCH) | Recruitment, RecruitmentSlot |
| `applications` | 応募・承認・参加管理(F-APP, F-DSC) | Application |
| `notifications` | サイト内通知(F-NTF) | Notification |
| `moderation` | 通報・ブロック・制裁(F-SAFE)。運営操作は Django Admin に集約 | Report, Block |

---

## 4. DB スキーマ(主要テーブル)

REQUIREMENTS.md 7 章のデータモデルを Django モデルとして具体化する。

### accounts_user(Django カスタムユーザー)

| カラム | 型 | 制約 |
|---|---|---|
| id | bigint | PK |
| discord_id | varchar | **unique**, not null(F-UNIQ-02) |
| discord_created_at | timestamptz | Snowflake から算出して保存(F-UNIQ-07) |
| discord_name / avatar_url | varchar | |
| riot_game_name / riot_tagline | varchar | 表示用 Riot ID |
| riot_puuid | varchar | **unique**, nullable(未連携を許す。連携完了までは応募・募集不可) |
| rank_solo / rank_flex | varchar | Riot API 取得値のみ(F-ACC-06)。手入力経路を作らない |
| rank_fetched_at | timestamptz | F-ACC-08 |
| lanes | jsonb | 例 `["TOP","MID"]` |
| play_hours / vc_style / bio | | |
| status | varchar | `active` / `warned` / `suspended` |
| is_staff / is_superuser | bool | Django Admin 用 |
| created_at / deleted_at | timestamptz | 退会は論理削除 + 個人情報カラムの null 化(F-ACC-07) |

### accounts_sanctionrecord

| カラム | 型 | 備考 |
|---|---|---|
| discord_id | varchar, indexed | **user FK ではなく discord_id で保持** — 退会後も残り、再登録時に引き継ぐ(F-UNIQ-04) |
| type / reason / created_at | | type: `warning` / `suspension` |

### games_game

| カラム | 備考 |
|---|---|
| name, slug | 例: `league-of-legends` |
| modes | jsonb: `["ランク(フレックス)", "ランク(デュオ)", ...]` |
| lanes | jsonb: `["TOP","JG","MID","ADC","SUP","FILL"]` |
| rank_tiers | jsonb: `["アイアン", ..., "チャレンジャー"]`(順序 = 配列順) |

> LoL 固有値はすべてこのマスタに置き、コードはマスタ参照のみとする(N-11)。初期データは fixture で投入。

### recruitments_recruitment

| カラム | 備考 |
|---|---|
| game FK / owner FK | |
| mode | games.modes の値 |
| rank_min_idx / rank_max_idx | rank_tiers の配列インデックスで保持(範囲検索を整数比較にするため。null = 指定なし) |
| start_at / duration_label | |
| vc_required / vc_tool | |
| tags | jsonb(定義済みタグのみ。バリデーションで担保) |
| comment | NG ワードフィルタ対象(F-SAFE-08, Should) |
| discord_invite_url | **一覧・詳細のクエリでは select しない**。参加者判定を通ったビューのみ参照(F-DSC-02, N-06) |
| status | `open` / `filled` / `closed` / `expired` |

### recruitments_recruitmentslot

| カラム | 備考 |
|---|---|
| recruitment FK / lane | |
| member FK(nullable) | null = 空き枠。owner も自分の枠を 1 つ持つ |

### applications_application

| カラム | 備考 |
|---|---|
| recruitment FK / applicant FK | **unique together**(F-APP-05 重複応募禁止) |
| desired_lane / comment | |
| status | `pending` / `approved` / `rejected` / `withdrawn` / `declined` |

### その他

- `notifications_notification`: user FK, type, payload(jsonb), read_at
- `moderation_report`: reporter FK, target_type/target_id, reason(choices に「サブ垢・スマーフの疑い」), detail, status
- `moderation_block`: user FK, blocked_user FK, unique together
- `applications_review`(GG レビュー)はテーブルだけ用意し UI はフェーズ 2(F-SAFE-03)

---

## 5. 主要処理フロー

### 5.1 ログイン・登録(F-ACC-01, F-UNIQ-02/04/07)

1. allauth の Discord プロバイダで OAuth2(scope: `identify`)
2. コールバックで Discord ID を取得し、Snowflake から作成日時を算出
   - `作成日時 = (discord_id >> 22) + 1420070400000`(ms)
   - **作成 3 ヶ月未満なら登録拒否**(設定値 `MIN_DISCORD_ACCOUNT_AGE_DAYS=90`)
3. 同一 discord_id の `SanctionRecord` を照会し、凍結歴があれば登録拒否/制限付き登録
4. 既存ユーザーなら通常ログイン(discord_id unique 制約が二重登録を防ぐ)
5. 初回登録時は利用規約・ガイドライン同意(F-SAFE-06)→ プロフィール設定 → Riot 連携へ誘導

### 5.2 Riot 連携・ランク取得(F-ACC-03/06/08, F-UNIQ-03, N-13)

1. ユーザーが Riot ID(ゲーム名 + タグライン)を入力
2. `Account-V1 /riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}` で PUUID を取得(実在確認)
3. PUUID の unique 制約により、他ユーザー登録済みならエラー(F-UNIQ-03)
4. `League-V4`(PUUID からランクエントリ取得)でソロ/フレックスのランクを保存、`rank_fetched_at` 更新
5. キャッシュ: Riot API レスポンスは Redis に TTL 24h で保存。手動更新ボタンはクールダウン(例: 10 分)付き
6. 定期更新: Celery Beat が毎日、アクティブユーザー(直近 7 日ログイン)のランクをレートリミット内で逐次再取得
7. 注意: 本人所有の確認(他人の Riot ID を登録する なりすまし)は Riot Sign On(RSO)が必要。**MVP では PUUID 一意性 + 通報で運用し、RSO はフェーズ 2 検討**として REQUIREMENTS に追記する余地あり

### 5.3 募集ライフサイクル(F-REC-05/06/07)

- 作成時: slots を同時生成、owner を自分の枠に割当
- `filled` 遷移: 応募承認時に空き枠が 0 になったら自動で成立 + 参加者へ集合案内通知(F-DSC-03)
- `expired` 遷移: Celery Beat の毎分ジョブで `status=open AND start_at < now()` を一括更新
- 編集・締切・削除は owner のみ。参加者がいる募集の変更・削除は通知を発行(F-NTF-04)

### 5.4 応募・承認(F-APP)

- 応募条件チェック: ログイン済み + Riot 連携済み + `status=open` + 自分の募集でない + ブロック関係なし(F-SAFE-02)+ 重複なし
- ランク帯チェック(F-SAFE-09, Should): 応募者の API 取得ランクが rank_min〜max 外なら警告表示(MVP では警告のみ、応募不可化は設定で切替可能に)
- 承認はトランザクション内で「空き枠の確認 → slot に割当 → application を approved」を行い、同時承認の競合を防ぐ(`select_for_update`)

### 5.5 Discord 招待リンクの表示制御(F-DSC-02, N-06)

- ビュー層で「閲覧者が owner または approved な参加者」の場合のみ `discord_invite_url` をテンプレートへ渡す
- 一覧 API/ページのシリアライズ対象から常に除外(モデルの `Meta` レベルでなくクエリの `defer`/明示 select で徹底)

### 5.6 通知(F-NTF-01/02/04)

- MVP はサイト内通知のみ: イベント発生箇所(応募作成、承認/見送り、募集変更・削除、成立)で Notification レコードを同期作成
- ヘッダーに未読バッジ表示。Discord DM(Bot)はフェーズ 2(F-NTF-05)

---

## 6. 画面とルーティング(プロトタイプとの対応)

| URL | ビュー | プロトタイプ |
|---|---|---|
| `/` | 募集一覧 + フィルタ(GET パラメータ) | `index.html` |
| `/recruitments/new` | 募集作成 | `recruit-new.html` |
| `/recruitments/<id>` | 募集詳細 + 応募 | `recruit-detail.html` |
| `/recruitments/<id>/applications` | 応募者管理(owner のみ) | `mypage.html` 内 |
| `/mypage` | プロフィール・自分の募集・応募中 | `mypage.html` |
| `/accounts/discord/login` ほか | allauth 標準 | — |
| `/admin/` | Django Admin(通報対応・凍結 = F-SAFE-07) | — |

既存プロトタイプの `assets/style.css` はそのまま Django の static に移植し、サンプルデータ描画 JS はテンプレート描画に置き換える。

---

## 7. セキュリティ・運用

- Django 標準の CSRF / セッション / パスワードレス(OAuth のみ)構成。`SECURE_*` 設定で HTTPS 強制(N-05)
- OAuth クライアントシークレット・Riot API キーは環境変数で注入(N-04)。リポジトリにコミットしない
- Riot API キー: 開発は Development Key、公開前に **Production Key を申請**(N-14。承認に日数がかかるため早めに申請)
- レートリミット対応: httpx クライアントに共通ラッパーを作り、429 の `Retry-After` 尊重 + Redis でアプリ側スロットリング
- ログ: 構造化ログ(JSON)+ Sentry。モデレーション操作は Django Admin の LogEntry で監査可能
- バックアップ: マネージド PostgreSQL の自動バックアップ(日次)を利用

### デプロイ先の推奨

| 候補 | 評価 |
|---|---|
| **Render**(推奨) | Web + Worker + Cron + マネージド Postgres/Redis が一通り揃い、無料〜低額で開始可能 |
| Railway | 同等。料金体系が従量制 |
| Fly.io | 柔軟だが構成の手数が多い |

---

## 8. 開発マイルストーン

| # | 内容 | 完了条件 |
|---|---|---|
| M1 | プロジェクト雛形(Django + Docker Compose + CI)、ゲームマスタ、カスタムユーザー | ローカルで起動し Admin にログインできる |
| M2 | Discord OAuth ログイン + 一意性チェック(作成日時・凍結歴) + 規約同意 | 新規登録〜プロフィール設定が通る |
| M3 | Riot 連携(実在確認・ランク取得・キャッシュ・手動/定期更新) | ランクがプロフィールに自動表示される |
| M4 | 募集 CRUD + 一覧フィルタ + 自動期限切れ | プロトタイプ同等の一覧・詳細・作成が動く |
| M5 | 応募・承認・成立 + 招待リンク表示制御 + サイト内通知 | 2 ユーザーで応募→承認→集合案内まで通しで動く |
| M6 | 通報・ブロック・Admin 運営フロー、NG ワード | 通報→Admin で凍結→再登録拒否が動く |
| M7 | 本番デプロイ・Sentry・バックアップ確認・Production API Key | 本番 URL で一連の動作確認 |

---

## 9. 未決事項

| 項目 | 内容 | 状況 |
|---|---|---|
| Riot ID の本人所有確認 | PUUID 一意性だけでは「他人の Riot ID を先に登録する」なりすましを防げない | **決定済み**: MVP は通報運用、フェーズ 2 で Riot Sign On(RSO)導入を検討(REQUIREMENTS F-ACC-09 に反映済み) |
| Discord アカウント年齢のしきい値 | 90 日で開始するか | 90 日で開始し、登録離脱率を見て調整 |
| サービス名・ドメイン | 仮称のまま | 実装着手前に決定 |
