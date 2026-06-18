# Riot API 申請キット(Production API Key)

Riot Developer Portal でアプリ(Product)を登録し、Production API Key を取得する
ための準備資料。**Riot の審査は英語で行われ、審査官は非ログイン状態でサイトを確認
する**ため、英語の回答文と、サイト側の前提条件をまとめている。

申請ページ: https://developer.riotgames.com/ → 「REGISTER PRODUCT」→「PERSONAL API KEY」
または「PRODUCTION API KEY」。一般公開する Web アプリは PRODUCTION を申請する。

---

## 0. 申請前チェックリスト(これが揃っていないと却下されやすい)

- [ ] **本番 URL が公開され、誰でもアクセスできる**(審査官がアクセスする。`DEPLOYMENT.md` で Render 等にデプロイ)
- [x] **プライバシーポリシーが公開ページにある** → `/privacy/`(実装済み。`【…】`の運営者名・連絡先・日付を埋める)
- [x] **利用規約が公開ページにある** → `/terms/`(実装済み。同上)
- [x] **Riot の法的免責表記がサイトに掲示されている**(実装済み。全ページのフッター)
- [ ] **ランクが自己申告でなく API 由来であることが画面で分かる**(実装済み: マイページに「✓ Riot API 連携済み」と取得日時)
- [ ] **無料サービスである**(課金要素なし)
- [ ] Discord OAuth が動作し、ログイン〜Riot 連携まで一連で試せる状態
- [ ] レート制限を守る実装(キャッシュ・429 対応)→ 本書「レート制限対応」を回答に使う

> まず Development Key で本番にデプロイして動作させ、上記を満たした状態で申請するのが通りやすい。

---

## 1. 申請フォームの回答(英語・コピペ用)

> 日本語の補足は `※` で記載。フォームの項目名は時期により多少異なる。

**Product Name**
```
NEONQ
```

**Product URL** ※公開済みの本番 URL
```
https://<your-domain>
```

**Privacy Policy URL**
```
https://<your-domain>/privacy/
```

**Terms of Service URL**
```
https://<your-domain>/terms/
```

**Game** : `League of Legends`

**Will your product be monetized?** : `No`
※無料。広告・課金・サブスクなし。

**Product Description**
```
NEONQ is a free web service for Japanese League of Legends players to find
teammates for ranked, normal, and ARAM games. Players sign in with Discord,
link their Riot ID, and create or apply to "recruitment" posts that specify
game mode, lanes, target rank range, start time, and voice-chat preference.
Once a party is full, approved members see a Discord invite to meet up.

We use the Riot API only to (1) verify that a submitted Riot ID exists and
(2) display each user's current ranked tier, which is fetched automatically
from the API rather than self-reported. This keeps the matchmaking honest and
prevents smurfing/rank misrepresentation. Ranks are cached and refreshed at
most once per day per active user.

The product is free, has no betting or gambling features, and does not imply
any endorsement by Riot Games (a legal disclaimer is shown site-wide).
```

**APIs / Endpoints used**
```
- Account-V1   : /riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}   (regional: asia)
- Summoner-V4  : /lol/summoner/v4/summoners/by-puuid/{puuid}                  (platform: jp1)
- League-V4    : /lol/league/v4/entries/by-summoner/{summonerId}             (platform: jp1)
```

**How do you handle rate limits? / Expected request volume**
```
Riot API responses are cached in Redis for 24 hours, so repeated profile views
do not hit the API. Rank refresh is the only recurring call: it runs once per
day via a scheduled job, iterating active users sequentially with a delay
between requests, and respects 429 Retry-After headers. User-triggered manual
refresh is rate-limited per user (10-minute cooldown). Expected volume is well
within the default development limits during launch (low thousands of calls/day).
```

**Target audience / region** : `Japan (JP1 / asia routing)`

---

## 2. Riot ポリシー遵守(申請時に確認される主な点)

| 項目 | 本サービスの対応 |
|---|---|
| 無料であること | 課金・広告なし(F フェーズ1で収益化しない) |
| ベッティング/ギャンブル禁止 | 該当機能なし |
| Riot 公認と誤認させない | 全ページに英語の法的免責 + 商標表記(実装済み) |
| プライバシーポリシー | `/privacy/` を公開(取得データ・第三者連携・削除を明記) |
| レート制限の遵守 | キャッシュ + 日次バッチ + 429 対応(実装済み) |
| データの適切な取り扱い | API キーはサーバー側管理、退会時削除、HTTPS |

---

## 3. 申請後の設定

1. 取得した Production API Key を本番環境変数 `RIOT_API_KEY` に設定(Render では `neonq-shared` グループ)。
2. `RIOT_PLATFORM=jp1` / `RIOT_REGIONAL=asia` を確認。
3. マイページの「更新」ボタンと日次 cron(`refresh_ranks`)でランク取得が成功することを確認。

---

## 4. サイト側で「埋めるべき」プレースホルダ

公開前に以下を実際の値へ置き換える:

- `templates/pages/terms.html` / `templates/pages/privacy.html` の
  `【運営者名】`、`【連絡先(メール / 公式 Discord 等)】`、`【YYYY年MM月DD日】`
- 本番ドメインを `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` に設定

---

## 5. 注意点

- **Development Key は約24時間で失効**する。本番公開までのテストは Dev Key、公開時に Production Key へ切り替える。
- Production Key の審査には数日〜かかることがある。デプロイと並行して早めに申請する。
- 本人所有確認(他人の Riot ID 登録の防止)は API だけでは担保できない。MVP は通報運用、将来 Riot Sign On(RSO)導入を検討(REQUIREMENTS F-ACC-09)。
