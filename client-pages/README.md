# お客様用 動画ライブラリ

クライアントごとに別ページ（別リンク）を作り、その会社のデータだけを埋め込みます。
社内向けの項目（編集者・単価・制作カルテ・メモ）は入れません。

更新手順（Claude に「お客様用ページを更新して」と頼めば同じことをします）:

1. ArtifactData `list` で `clients` / `videos` / `metrics` を `out_dir=<dump>` に保存
2. `python3 client-pages/build.py <dump> <out>`
3. 各 `<out>/<clientId>.html` を、ハブの `clients/<id>.libraryUrl` の URL に Artifact publish（`url` 指定で同じリンクを更新）

## 動画一覧PDF（Claudeを使っていないお客様向け）

管理画面のクライアントタブ（またはレポート画面）の「動画一覧PDFをドライブに保存」を押すと、
ブラウザ上でPDFを作り、Googleドライブの「お客様用 動画一覧PDF / <社名> 様 動画一覧」フォルダに保存する。
PDF内のボタン（動画を見る・YouTube）はリンクとして押せる。保存し直すと前のPDFはゴミ箱に移る。

お客様に送るのはフォルダのリンク。初回だけ、各フォルダを ドライブで「共有 → 一般的なアクセス →
リンクを知っている全員（閲覧者）」にする。中のPDFは毎回自動でその共有設定になる。
共有がまだのフォルダは管理画面に「共有設定がまだです」と表示される。

`pdf.py` は同じページをサーバー側でPDFにする予備の方法（headless Chromium）:
`python3 client-pages/pdf.py <out_dir> [clientId ...]`（build.py が書いた `<id>.print.html` を印刷）。
