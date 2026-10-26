# 企画・PDCA の自動処理

動画管理基盤（https://claude.ai/artifact/4pZJWTGijjWY4RJ5tPUbAc）の「企画・PDCA」タブのボタンから、
Claude Code Remote の `fire_trigger` で呼ばれるルーティンの手順です。追加テキストに `clientId: <id>` が入ります。

| ボタン | ルーティン | 手順 |
|---|---|---|
| 学びからリサーチ | SNSリサーチ（学びから） | [RESEARCH.md](RESEARCH.md) |
| フィードバック＆分析 | SNS振り返り・分析 | [ANALYZE.md](ANALYZE.md) |

- `search.py`：学びの検索語から YouTube（検索ページ）・Instagram（ハッシュタグのリール）・TikTok（検索）の候補を集める
- `score.py`：過去動画の判定（中央値比）と、学びの検証回数・更新案を出す（ローカルの sns-kikaku スキルと同じもの）

## 共通のルール

- 処理の状態は `researchRequests/<kind>_<clientId>`（kind は `research` か `analyze`）に書く。
  始めたら `status: "running"`、終わったら `status: "done"`・`doneAt`（ISO）・`note`（結果のひとこと、60字まで）、
  リサーチなら `added`（登録した本数）。失敗したら `status: "error"` と `note` に理由。
- 学びは消さない・上書きしない。根拠（`evidence`）は日付付きで **追記** する。
- 既存のドキュメントを変えるときは、読んだときの `version` を `if_version` に入れて `update` で必要な項目だけ変える。
  書き込みは ArtifactData の `batch`（50件まで）でまとめる。
- 画面は複数人で見るので、書いた内容はそのまま他の人にも見える。お客様に出せない言葉は書かない。
- 人への確認はしない（ボタンを押した時点で依頼済み）。最後に日本語で2〜3行の報告をして終わる。

## データの形（動画管理基盤のコレクション）

- `clients`：`name`・`aliases`・`industry`（car／food／house／beauty／retail／recruit／other）・`ig`/`tt`/`yt`（アカウントURL）・`refs`（競合）
- `metrics`：`<clientId>_<YYYY-MM>`。`videos:[{platform(ig/tt/yt), kind(short/long), title, url, date, views, likes, comments}]`
- `videos`：案件管理シートから同期した案件（`title`＝案件名、`clientId`、`postDate`、`status`、`docUrl`＝制作カルテのGoogleドキュメント）
- `learnings`：`text`・`area`（content／edit／client）・`type`（win／lose／hypo）・`status`（検証中／確定／棄却）・`clientId`（空＝業種全体）・
  `industry`・`platforms`（ig／tt／yts／ytl）・`evidence`・`queries`（1行1つ）・`count`（フィードバックの回数）・`updatedAt`
- `research`：`url`・`title`・`platform`（tt／ig／yts／ytl）・`views`・`account`・`postedAt`・`source`（YouTube検索／Instagram検索／TikTok検索／競合・参考アカウント）・
  `hook`・`format`・`why`・`learningId`・`clientId`・`industry`・`foundAt`
- `plans`：`clientId`・`title`・`status`（企画／クライアント確認／撮影済／投稿済／検証済／見送り）・`kind`（exploit／explore）・`learningIds`・
  `hypothesis`・`hook`・`format`・`postUrls`・`review`

`hook` は 結論先出し／問いかけ／ビフォーアフター／衝撃映像・数字／あるある・共感／ランキング・比較／失敗・注意喚起／ストーリー／その他 のどれか。
`format` は 作業工程／解説・知識／商品・車両紹介／お客様の声／スタッフ・裏側／ビフォーアフター／トレンド・ネタ／その他 のどれか。

ドキュメントIDは `lr_<clientId か業種>_<連番>`・`rs_<clientId か業種>_<YYYYMMDD>_<連番>`。既にあるIDと重ならない番号にする。

## 判定ルール

- 中央値比＝その動画の再生数 ÷ 同じクライアント・同じ媒体（IG／TT／YTショート／YT横）の直近3か月の再生数の中央値
- 1.5倍以上＝勝ち、0.6倍以下＝負け、その間＝平均、投稿から14日未満＝保留
- 学びの状態：同じ向きの結果が2回以上で、逆の結果より多ければ変える（勝ち・仮説は2勝で確定、2敗で棄却。負けパターンは逆）

## 手順ファイルの更新

ローカルから push できないときは、変更をパッチにして動画管理基盤の `deploy/pdca_latest`（`version`・`patch`・`sha256`）に置く。
ルーティンは最初に `pdca/VERSION`（無ければ 1）と比べ、新しければ sha256 を確かめて `git am` し、このブランチに push する。
