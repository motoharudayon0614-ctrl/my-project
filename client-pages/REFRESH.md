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

## 公開ページ（ログイン不要・GitHub Pages）も更新する

Claude を使っていないお客様向け。リンクを知っている人だけがログインなしで開ける（noindex・robots.txt で検索除外）。
URL は `https://motoharudayon0614-ctrl.github.io/my-project/v/<publicSlug>/` で、`clients/<id>.publicSlug` に保存済み（更新してもリンクは変わらない）。

7. `python3 client-pages/public.py <dump> <out> <site>` を実行（`<out>` は手順3の出力）。
   出力 JSON の `newSlugs` / `newNos` にあるクライアント（新規）は、`clients/<id>` に `publicSlug`・`publicUrl`・`publicNo` を if_version 付き update で書く。
   同時に `l/a8Qm3vTzK7pWn2Rx.csv`（No・会社名・公開リンク・動画本数・更新日時）も出力される。管理用のGoogleスプレッドシート「動画ライブラリ 公開リンク一覧」がこれを IMPORTDATA で読み込むので、push すれば一覧表も自動で最新になる。
8. `gh-pages` ブランチを別ディレクトリに checkout し（`git worktree add <dir> gh-pages`）、`v/` と `l/` を消してから `<site>` の中身をコピーし、commit・push する。
