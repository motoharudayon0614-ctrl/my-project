# お客様用ページの更新（ルーティン「お客様用ページ更新」が実行）

管理画面（https://claude.ai/artifact/4pZJWTGijjWY4RJ5tPUbAc）の「お客様用ページを更新」ボタンから呼ばれる。
追加テキストの `clientIds:` 行に対象（カンマ区切り、`all` なら全社）が入る。人への確認は不要。

1. リポジトリ motoharudayon0614-ctrl/my-project を用意し、ブランチ `claude/new-session-ynydo4` を checkout。
2. ArtifactData（ToolSearch で読み込む）で管理画面の `clients` / `videos` / `metrics` を
   `list`（limit 1000, `out_dir=<dump>`）で保存する。
3. `python3 client-pages/build.py <dump> <out>` を実行。出力は `<out>/<clientId>.html`。
4. 対象クライアントごとに:
   - `clients/<id>` に `libraryUrl` があれば、まず Artifact `read`（url=libraryUrl）してから、
     Artifact publish（file_path=`<out>/<id>.html`, url=libraryUrl）で同じリンクを更新する。
   - `libraryUrl` が無ければ、Artifact publish（icon は video）で新しく作り、そのURLを控える。
   - `<out>/<id>.html` が無い（動画0件など）場合は飛ばす。
5. ArtifactData `update`（if_version 付き）で対象の `clients/<id>` に
   `libraryUpdatedAt`（実際の時刻。`date -u +%Y-%m-%dT%H:%M:%SZ` の出力をそのまま使い、推測で書かない）, `libraryStatus: "done"`（失敗なら `"error"` と `libraryError`）,
   新規作成した場合は `libraryUrl` を書く。50件ずつ `batch` でまとめる。
6. 更新した社数・失敗したクライアントを日本語で短く報告する。
