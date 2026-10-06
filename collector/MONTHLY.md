# 月次の自動取得（毎月1日）

動画管理基盤（https://claude.ai/artifact/4pZJWTGijjWY4RJ5tPUbAc）に登録したクライアントのアカウントURLから、
Apify で公開データ（ログイン不要）を取得し、前月分の数値をハブの `metrics` に書き込む手順です。
毎月1日に Claude のルーティンがこの手順を実行します。

## 前提（初回のみ・人が設定）

1. Apify のアカウントを作り、API トークンを発行する（Settings → API & Integrations）。
2. Claude Code のクラウド環境設定（セッション上部の環境メニュー → Edit）で
   - 「API認証情報」に api.apify.com 用のトークンを登録する（環境変数 `APIFY_TOKEN` でも可）
   - ネットワークアクセスで `api.apify.com` に接続できるようにする（Custom にして Allowed domains に追加）

## 手順（ルーティンが実行）

1. `git fetch origin claude/new-session-ynydo4 && git checkout claude/new-session-ynydo4`
2. `curl -s -o /dev/null -w '%{http_code}' https://api.apify.com/v2/users/me` が 200 を返すことを確認する
   （`APIFY_TOKEN` があれば `-H "Authorization: Bearer $APIFY_TOKEN"` を付ける。API認証情報で登録した場合は付けなくても通る）。
   000 なら接続が許可されていない、401 ならトークンが届いていない。だめなら何も書き込まず、どちらが足りないかを報告して終了する。
3. ArtifactData `list`（collection `clients`, limit 1000）でクライアントを取得し、各ドキュメントの `id` を含めて `clients.json` に保存する。
4. `python3 collector/collect.py clients.json --out metrics.json`（対象月は日本時間の前月が自動で入る）。
5. `metrics.json` の `docs` ごとに、ハブの `metrics/<docId>` を ArtifactData `get` し、
   - 存在する → `update`（`if_version` 付き）で `data` をマージする。手入力の所感 `note` などは残る。
   - 存在しない → `set` で作成する。
   書き込みは `batch`（50件ずつ）でまとめる。
6. 取得できた社数、`errors` の内容、URL未登録や取得できなかったクライアントを短く報告する。
