# お客様用 動画ライブラリ

クライアントごとに別ページ（別リンク）を作り、その会社のデータだけを埋め込みます。
社内向けの項目（編集者・単価・制作カルテ・メモ）は入れません。

更新手順（Claude に「お客様用ページを更新して」と頼めば同じことをします）:

1. ArtifactData `list` で `clients` / `videos` / `metrics` を `out_dir=<dump>` に保存
2. `python3 client-pages/build.py <dump> <out>`
3. 各 `<out>/<clientId>.html` を、ハブの `clients/<id>.libraryUrl` の URL に Artifact publish（`url` 指定で同じリンクを更新）
