# 開発フロー(GitHub Flow)

NEONQ は **GitHub Flow** で運用する。`main` は常にデプロイ可能な本番ブランチで、
Render が `main` を追跡して自動デプロイする。

## 基本ルール

1. `main` には直接 push しない。必ずブランチ + Pull Request 経由。
2. 作業ごとに `main` から短命なブランチを切る。
3. PR を作成 → CI(テスト・ruff・マイグレーション差分)が緑 → レビュー → `main` にマージ。
4. マージで Render が自動デプロイ。

## ブランチ命名

| 用途 | 例 |
|---|---|
| 機能追加 | `feature/discord-dm-notifications` |
| 不具合修正 | `fix/rank-cache-ttl` |
| 雑務・設定 | `chore/bump-django` |
| ドキュメント | `docs/update-readme` |

## コミット / PR

- コミットメッセージは「何を・なぜ」を簡潔に。日本語可。
- PR には目的と確認内容を書く。CI が通らないものはマージしない。
- 履歴を簡潔に保ちたい場合は **Squash and merge** を推奨。

## ローカルでの確認(マージ前に最低限)

```bash
python manage.py test
ruff check .
python manage.py makemigrations --check --dry-run
```

## 環境とブランチの対応

| ブランチ | 環境 |
|---|---|
| `main` | 本番(Render → neonq.online) |
| `feature/*` 等 | ローカル / PR の CI のみ(常設環境なし) |

> ステージング環境が必要になったら、`develop` ブランチ + Render の別サービスを足す
> 形(Gitflow-lite)へ拡張できる。現状は不要。

## ブランチ保護(GitHub 側で設定)

`main` を事故から守るため、GitHub の Settings → Branches で次を設定する:

- **Require a pull request before merging**(直接 push を禁止)
- **Require status checks to pass before merging** → チェックに `test`(CI)を指定
- (任意)**Require branches to be up to date before merging**
