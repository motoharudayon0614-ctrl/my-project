# フィードバック＆分析（ボタン「フィードバック＆分析」）

先に [README.md](README.md) の共通のルールとデータの形を読む。追加テキストの `clientId:` が対象。
やること：過去動画の判定 → 企画の振り返り → 学びの検証回数と状態の更新 → 新しい仮説 → 制作カルテの修正指示をフィードバックの学びに取り込む。

1. ブランチ `claude/new-session-ynydo4` を checkout する。ArtifactData は ToolSearch で読み込んでから使う。Google Drive も ToolSearch で読み込む（制作カルテを読むため）。
2. `researchRequests/analyze_<clientId>` を `status: "running"` にする。
3. 作業フォルダ `work/` を作り、ArtifactData で書き出す（`out_dir` を `work` にする）：
   - `metrics`・`plans`・`videos` は `query`（`where: [["clientId","==",<id>]]`、limit 1000）
   - `learnings`・`research` は `list`（limit 1000）
   書き出したファイルの名前は `work/<collection>.json` にそろえる（score.py がこの名前で読む。中身は `[{id, version, data}]` か `{docs:[...]}` のどちらでもよい）。
4. `python3 pdca/score.py --db-dir work --client <clientId>` を実行する。出てくるのは、媒体ごとの動画の判定・企画ごとの判定・学びごとの検証回数と更新案。
5. 企画の振り返り：判定が出た企画（勝ち・平均・負け）で `review` が空のものに、何が当たり何が外れたか・次にどうするかを2〜3文で書き、`status` を「検証済」にする。
6. 学びの更新：
   - score.py の更新案どおりに `status`（仮説が2勝なら `type` も `win`）を変える
   - その学びの企画の結果を `evidence` の末尾に「YYYY-MM 企画名：媒体 X.X倍（勝ち／負け）」と1行追記する。同じ企画名の行が既にあれば書かない
   - 勝ち・負けの動画（企画につながっていないものも含む）から新しく見えた傾向があれば、`hypo`（検証中）として追加する。
     媒体限定なら `platforms` を入れ、`evidence` に根拠の動画と倍率、`queries` に次に探す条件を書く。根拠のない思いつきは書かない
   - 学びごとに `queries` を見直す（確定した勝ちは「同じ型の別の題材」、検証中は「同じ型で伸びている例」、負けは「例外的に伸びた反証」）
7. フィードバックの取り込み：`videos` のうち `docUrl` が Googleドキュメントで、`postDate` か最終更新が直近60日以内のものを新しい順に最大10件読む
   （Google Drive の `read_file_content`。ファイルIDは URL の `/d/<id>/` の部分）。
   - 「修正1〜」欄と「質問内容＆回答」の指摘を1つずつ見る。空欄・「なし」は飛ばす
   - 既にあるフィードバックの学び（`area` が `edit` か `client`）と同じ内容なら、`evidence` に「案件名（修正n）」が無いときだけ
     `count` を1増やし、`evidence` の末尾に「YYYY-MM 誰：案件名（修正n）」を追記する。2回以上で `status` を「確定」にする
   - 新しい指摘なら学びを追加する：編集の技術（テロップ・SE・カット・BGM など）は `area: edit`・`clientId` 空（全社共通）、
     そのお客様の好み・NG・表記・使えない素材は `area: client`・そのクライアント。`type: win`・`status: 検証中`・`count: 1`
   - 誰の指摘かを必ず書く（西村さん＝編集チェック、シオヤさん、記入者なし＝お客様の可能性）
   - 読めないドキュメントは飛ばして、報告に件数を書く
8. 5〜7 の変更を `batch` でまとめて書き込む（既存は `if_version` 付き `update`、新しい学びは `set`）。`updatedAt` も入れる。
9. `researchRequests/analyze_<clientId>` を `status: "done"`・`doneAt`・`note`（例「振り返り2件・学び更新3件・新しい仮説1件・フィードバック2件」）にする。
   途中で失敗したら `status: "error"`・`note` に理由を書いて終わる。
10. 報告：確定・棄却になった学び、新しい仮説、取り込んだフィードバック、振り返りを書いた企画。
