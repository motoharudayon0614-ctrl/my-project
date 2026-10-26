#!/usr/bin/env python3
"""過去動画と企画の成績を採点する（動画管理基盤の「企画・PDCA」タブと同じルール）。

使い方:
  python3 score.py --db-dir <dir> --client <clientId> [--today YYYY-MM-DD]

--db-dir : ArtifactData の out_dir で書き出したフォルダ。<dir>/metrics/*.json・<dir>/plans/*.json・
           <dir>/videos/*.json（制作管理シートから同期された案件）を読む。plans と videos はなくてもよい。
判定ルール:
  中央値比 = 再生数 ÷ 同じクライアント・同じ媒体（IG / TT / YTショート / YT横）の直近3か月の再生数中央値
  1.5 以上 = 勝ち / 0.6 以下 = 負け / その間 = 平均 / 投稿から14日未満 = 保留
企画と動画の突き合わせ: 投稿URL → キャプションに案件名を含む動画（シートの投稿日±7日）→ 投稿日±1日にその媒体で1本だけの動画
学び: <dir>/learnings/*.json があれば、企画の learningIds から検証回数を数え、2勝で「確定」・2敗で「棄却」の更新案を出す
"""
import argparse, glob, json, os, statistics, unicodedata
from datetime import date, timedelta

WIN, LOSE, MIN_DAYS, MONTHS = 1.5, 0.6, 14, 3
PK_NAME = {"ig": "Instagram", "tt": "TikTok", "yts": "YouTube ショート", "ytl": "YouTube 横動画"}


def d(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def norm(s):
    return " ".join(unicodedata.normalize("NFKC", str(s or "")).split()).lower()


def pk(v):
    if v.get("platform") == "yt":
        return "yts" if (v.get("kind") or "long") == "short" else "ytl"
    return v.get("platform")


def docs(db, col, cid=None):
    out = []
    for f in glob.glob(os.path.join(db, col, "*.json")):
        x = json.load(open(f, encoding="utf-8"))
        x = x.get("data", x)
        x.setdefault("id", os.path.basename(f)[:-5])
        if cid is None or x.get("clientId") == cid:
            out.append(x)
    return out


def client_videos(db, cid):
    """同じ動画が複数の月のドキュメントに入るので、URLごとに最新の取得分だけ残す。"""
    best = {}
    for doc in docs(db, "metrics", cid):
        got = str(doc.get("collectedAt") or doc.get("updatedAt") or doc.get("month") or "")
        for v in doc.get("videos") or []:
            key = v.get("url") or (v.get("platform"), v.get("date"), v.get("title"))
            if key not in best or got > best[key][0]:
                best[key] = (got, dict(v, collected=got[:10], pk=pk(v)))
    return [v for _, v in best.values()]


def judge(v, med):
    if not med or not isinstance(v.get("views"), (int, float)):
        return None, "保留"
    ratio = v["views"] / med
    pd, seen = d(v.get("date")), d(v.get("collected"))
    if pd and seen and (seen - pd).days < MIN_DAYS:
        return ratio, "保留"
    return ratio, "勝ち" if ratio >= WIN else "負け" if ratio <= LOSE else "平均"


def label(r):
    return "勝ち" if r >= WIN else "負け" if r <= LOSE else "平均"


def match(plan, vids, sheet):
    urls = [u for u in (plan.get("postUrls") or {}).values() if u]
    hits = [v for v in vids if v.get("url") in urls] if urls else []
    post = d(plan.get("postDate"))
    if not post:
        row = next((s for s in sheet if norm(s.get("title")) == norm(plan.get("title"))), None)
        post = d(row.get("postDate")) if row else None
    key = norm(plan.get("title"))
    if not hits and len(key) >= 2:
        by = {}
        for v in vids:
            vd = d(v.get("date"))
            if key in norm(v.get("title")) and (not post or (vd and abs((vd - post).days) <= 7)):
                dist = abs((vd - post).days) if post and vd else 0
                if v["pk"] not in by or dist < by[v["pk"]][0]:
                    by[v["pk"]] = (dist, v)
        hits = [v for _, v in by.values()]
    if not hits and post:
        by = {}
        for v in vids:
            vd = d(v.get("date"))
            if vd and abs((vd - post).days) <= 1:
                by.setdefault(v["pk"], []).append(v)
        hits = [a[0] for a in by.values() if len(a) == 1]
    return hits, post


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-dir", required=True)
    ap.add_argument("--client", required=True)
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args()
    today = d(a.today)
    since = today - timedelta(days=30 * MONTHS)

    vids = client_videos(a.db_dir, a.client)
    recent = [v for v in vids if (d(v.get("date")) or today) >= since]
    meds = {}
    for p in PK_NAME:
        views = [v["views"] for v in recent if v["pk"] == p and isinstance(v.get("views"), (int, float))]
        if views and statistics.median(views) > 0:
            meds[p] = statistics.median(views)
    for v in vids:
        v["ratio"], v["judge"] = judge(v, meds.get(v["pk"]))

    print(f"# 採点結果（直近{MONTHS}か月 {since}〜{today}、{len(recent)}本）\n")
    for p, med in meds.items():
        rows = sorted((v for v in recent if v["pk"] == p), key=lambda v: -(v["ratio"] or 0))
        print(f"## {PK_NAME[p]}（再生数の中央値 {med:,.0f}）\n")
        print("| 判定 | 中央値比 | 再生数 | いいね | コメント | 投稿日 | キャプション | URL |")
        print("|---|---|---|---|---|---|---|---|")
        for v in rows:
            r = f"{v['ratio']:.2f}" if v["ratio"] is not None else "—"
            t = str(v.get("title") or "").replace("\n", " ").replace("|", "／")[:40]
            print(f"| {v['judge']} | {r} | {v.get('views', 0):,} | {v.get('likes', '—')} | {v.get('comments', '—')} | {v.get('date', '')} | {t} | {v.get('url', '')} |")
        print()

    plans = docs(a.db_dir, "plans", a.client)
    if not plans:
        return
    sheet = docs(a.db_dir, "videos", a.client)
    print("## 企画の結果\n")
    print("| 判定 | 平均の中央値比 | 企画 | 種別 | フック | 構成 | 仮説 | 投稿日 | 内訳 | plan id |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    results = {}
    for pl in sorted(plans, key=lambda x: x.get("createdAt") or ""):
        hits, post = match(pl, vids, sheet)
        results[pl["id"]] = hits
        ratios = [v["ratio"] for v in hits if v["ratio"] is not None]
        settled = [v["ratio"] for v in hits if v["ratio"] is not None and v["judge"] != "保留"]
        j = "未投稿" if not hits else label(sum(settled) / len(settled)) if settled else "保留"
        avg = f"{sum(ratios) / len(ratios):.2f}" if ratios else "—"
        parts = " / ".join(f"{v['pk']} {v.get('views', 0):,}回 {v['ratio']:.2f}倍" for v in hits if v["ratio"] is not None)
        print(f"| {j} | {avg} | {pl.get('title', '')} | {pl.get('kind', '')} | {pl.get('hook', '')} | {pl.get('format', '')} | "
              f"{str(pl.get('hypothesis') or '').replace('|', '／')[:40]} | {post or ''} | {parts} | {pl['id']} |")

    # 学びの検証回数：その学びを learningIds に持つ企画の判定を数える（platforms があればその媒体だけで判定）
    learns = [l for l in docs(a.db_dir, "learnings") if l.get("clientId") in ("", None, a.client)
              and l.get("area") not in ("edit", "client")]  # フィードバックは再生数ではなく指摘回数で数える
    if not learns:
        return
    print("\n## 学びの検証回数と更新案\n")
    print("| 学び | 種類 | 今の状態 | 判定に使う媒体 | 検証 | 勝ち | 負け | 結果待ち | 更新案 | learning id |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for l in learns:
        ps = l.get("platforms") or []
        w = lo = n = pending = 0
        for pl in plans:
            if l["id"] not in (pl.get("learningIds") or []):
                continue
            hits = [v for v in results.get(pl["id"], []) if not ps or v["pk"] in ps]
            done = [v["ratio"] for v in hits if v["ratio"] is not None and v["judge"] != "保留"]
            if not done:
                pending += 1
                continue
            j = label(sum(done) / len(done))
            n += 1
            w += j == "勝ち"
            lo += j == "負け"
        up, down = (lo, w) if l.get("type") == "lose" else (w, lo)
        want = "確定" if up >= 2 and up > down else "棄却" if down >= 2 and down > up else ""
        if want == l.get("status"):
            want = ""
        print(f"| {str(l.get('text') or '')[:40]} | {l.get('type', '')} | {l.get('status', '')} | {','.join(ps) or '全部'} | {n} | {w} | {lo} | {pending} | {want} | {l['id']} |")


if __name__ == "__main__":
    main()
