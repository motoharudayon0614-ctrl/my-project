# 即時更新（管理画面の「数字を更新」ボタン／URL登録時）

管理画面（https://claude.ai/artifact/4pZJWTGijjWY4RJ5tPUbAc）から Claude Code Remote の `fire_trigger` で
ルーティン「SNS数値の即時更新」が呼ばれたときの手順。追加テキストに `clientIds: id1,id2`（`all` なら全社）が入る。

1. リポジトリ motoharudayon0614-ctrl/my-project を用意し、ブランチ `claude/new-session-ynydo4` を checkout する。
2. `curl -s -o /dev/null -w '%{http_code}' https://api.apify.com/v2/users/me` が 200 であることを確認（API認証情報でトークンが付く）。
   200 でなければ 4. の失敗記録だけ書いて終了。
3. ArtifactData `list`（collection `clients`, limit 1000）→ 対象クライアント（`all` なら active が false 以外の全社）を
   `id` を含めて `clients.json` に保存し、`python3 collector/collect.py clients.json --month now --out metrics.json` を実行
   （今月と前月を1回の取得でまとめて作る）。
4. `metrics.json` の `docs` ごとに `metrics/<docId>` を get し、あれば `if_version` 付き `update`（所感 `note` は残る）、
   なければ `set`。対象クライアントごとに `clients/<id>` を `update` して
   `fetchStatus`（`done` / `error`）, `fetchedAt`（ISO 時刻）, `fetchError`（失敗理由。成功なら `{"__delete__": true}`）を書く。
   書き込みは `batch`（50件まで）でまとめる。
5. 取得できた社数と失敗理由を日本語で短く報告して終了。
