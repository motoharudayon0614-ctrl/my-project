# 学びからリサーチ（ボタン「学びからリサーチ」）

先に [README.md](README.md) の共通のルールとデータの形を読む。追加テキストの `clientId:` が対象。

1. ブランチ `claude/new-session-ynydo4` を checkout する。ArtifactData は ToolSearch で読み込んでから使う（URL は README の動画管理基盤）。
2. `researchRequests/research_<clientId>` を `status: "running"` にする（ボタン側で済んでいても上書きしてよい）。
3. 作業フォルダ `work/` に、`clients` を `get`（そのクライアント）、`learnings` と `research` を `list`（limit 1000）、
   `metrics` を `query`（`where: [["clientId","==",<id>]]`）で書き出す。
4. 探す学びを最大5つ選ぶ。対象は `area` が `content` か空で、`clientId` がそのクライアント、または空で `industry` が同じもの。
   順番：確定・検証中の勝ちパターン（`type: win`）→ 検証中の仮説（`hypo`）→ 負けパターン（`lose`、例外的に伸びた反証を探す）。棄却は使わない。
   同じ順位なら、そのクライアントの学び・`research` にまだ参考動画が少ない学びを先にする。
   - 内容の学びがまだ1つもないときは、`metrics` の動画から中央値比1.5倍以上の勝ち動画を見て、型を「検証中の仮説」（`type: hypo`、
     `status: 検証中`、`platforms`・`evidence`・`queries` 入り）として1〜3個作り、先に `learnings` に書いてから使う。
5. 学びごとに、`queries`（無ければ `text`）から検索語を作り、`work/plan.json` に書く：
   `[{"learningId": "...", "yt": ["検索語", ...], "tt": ["検索語"], "ig": ["ハッシュタグ"], "exclude": ["クライアント名", "アカウント名"]}]`
   - YouTube は2〜3個、TikTok は空（Apify を使わないため）、Instagram は1〜2個。どれも短く（2〜3語）、タイトルやキャプションに入りそうな日本語にする
   - Instagram はハッシュタグなので空白なしの1語（例 `自宅サウナ`、`サウナ好きな人と繋がりたい` は広すぎるので使わない）
   - 学びの `platforms` が1媒体だけなら、その媒体の検索語を多めにする
   - `exclude` にはクライアントの `name`・`aliases`、`ig`/`tt`/`yt` のアカウント名を入れる
6. **Apify（有料）を使うのは Instagram だけ**（料金を抑えるため。search.py の `--apify` の既定が `ig`）。TikTok は plan.json の `tt` を空にして探さない（ブラウザでの調査はシオヤさんが別に頼む）。YouTube は無料の検索ページだけで探し、開けなければ飛ばす。
    `curl -s -o /dev/null -w '%{http_code}' https://api.apify.com/v2/users/me` が 200 か確かめる。200 でなければ plan.json の `ig` も空にして、報告に書く。
7. `python3 pdca/search.py work/plan.json --out work/found.json --months 3 --min-views 100000 --limit 20` を実行する。
   **参考動画の条件（固定）：投稿日が直近3か月以内・再生10万回以上・広告/タイアップ/商品リンク付き/TikTokShop/アフィリエイト（「プロフィールのリンクから」等）ではないもの。**
   search.py は広告らしいものを自動で除く（`--allow-ads` は使わない）。
   条件を満たす動画が3本未満のときだけ `--min-views 50000` でもう一度取り、その旨を手順10の `note` に書く（例「10万回以上が少ないため5万回以上で補充」）。
8. `found.json` から、学びごとに1〜3本、合計5〜10本を選ぶ。選ぶ基準：
   - クライアントの業種・お客様に関係があり、型（フック・構成）を真似できる。関係のない広告・ドラマ・海外・芸能人頼みのものは選ばない
   - キャプションやアカウントから広告・案件・商品紹介アフィリエイトだと分かるものは、自動で残っていても選ばない
   - 投稿日が分からないもの（YouTube ショート等）は、日付が分かるものが足りないときだけ選び、`why` に「投稿日不明」と書く
   - `research` に同じ `url` があるものは選ばない
   - なるべく媒体を散らす（Instagram と YouTube）
9. 選んだものを `research` に `set` で登録する（`batch` で1回）：`url`・`title`（内容をひとこと）・`platform`・`views`・`account`・`postedAt`・
   `source`（YouTube検索／Instagram検索／TikTok検索）・`hook`・`format`（README の選択肢から）・`why`（伸びた理由。タイトル・キャプション・数字からの推測なので「推測：」を付ける）・
   `learningId`・`clientId`・`industry`・`foundAt`（今の ISO 時刻）
10. `researchRequests/research_<clientId>` を `status: "done"`・`doneAt`・`added`（本数）・`note`（例「YouTube 4本・TikTok 3本・Instagram 2本」）にする。
    途中で失敗したら `status: "error"`・`note` に理由を書いて終わる。
11. 報告：登録した本数（媒体別）、どの学びから探したか、Apify が使えなかった場合はその理由。
