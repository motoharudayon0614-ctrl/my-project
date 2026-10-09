#!/usr/bin/env python3
"""Build one private video-library page per client from a dump of the hub's database.

    python3 client-pages/build.py <dump_dir> <out_dir>

<dump_dir> holds clients/*.json, videos/*.json and metrics/*.json as written by
ArtifactData `list ... out_dir=<dump_dir>`. Each page embeds only that client's
rows, so a page shared with one client never contains another client's data.
Internal fields (editor, unit price, internal docs, memo) are not copied.
"""
import datetime as dt
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_NAMES = {"突発依頼", "(クライアント未記入)"}
DONE = {"完了", "格納済", "投稿済"}
WAIT = {"納品済", "クライアント確認"}


def load(dirpath):
    out = {}
    for f in glob.glob(os.path.join(dirpath, "*.json")):
        with open(f, encoding="utf-8") as fh:
            out[os.path.basename(f)[:-5]] = json.load(fh)
    return out


def status(s):
    return "done" if s in DONE else "wait" if s in WAIT else "wip"


def links(v):
    """Client-facing links only: Drive / YouTube / file-transfer URLs. Internal Google Docs are left out."""
    out, seen = [], set()
    store = [u for u in re.split(r"\s+", v.get("storeUrl") or "") if u.startswith("http")]
    for i, u in enumerate(store):
        if u not in seen:
            seen.add(u)
            out.append({"k": "動画を見る" if i == 0 else "動画%d" % (i + 1), "u": u})
    u = (v.get("url") or "").strip()
    if u.startswith("http") and u not in seen and "docs.google.com" not in u:
        k = "YouTube" if ("youtube.com" in u or "youtu.be" in u) else "納品データ" if "drive.google.com" in u else "ダウンロード"
        if not out and k == "納品データ":
            k = "動画を見る"
        out.append({"k": k, "u": u})
    return out


def sns_rows(metrics, cid):
    rows = []
    for doc in metrics.values():
        if doc.get("clientId") != cid:
            continue
        for v in doc.get("videos") or []:
            p = v.get("platform")
            if p == "yt":
                p = "yts" if (v.get("kind") or "long") == "short" else "ytl"
            if p not in ("ig", "tt", "yts", "ytl") or not v.get("date"):
                continue
            rows.append({"date": v["date"], "p": p, "title": v.get("title") or "", "url": v.get("url") or "",
                         "views": v.get("views"), "likes": v.get("likes")})
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows[:60]


def build(dump, out_dir):
    clients, videos, metrics = load(os.path.join(dump, "clients")), load(os.path.join(dump, "videos")), load(os.path.join(dump, "metrics"))
    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as fh:
        tpl = fh.read()
    jst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for cid, c in clients.items():
        name = (c.get("name") or "").strip()
        if not name or name in SKIP_NAMES or c.get("active") is False:
            continue
        rows = []
        for v in videos.values():
            if v.get("clientId") != cid:
                continue
            date = v.get("postDate") or ""
            month = (date or v.get("dueDate") or v.get("orderDate") or "")[:7]
            if not month:
                continue
            rows.append({"title": v.get("title") or "(無題)", "date": date, "due": v.get("dueDate") or "", "month": month,
                         "st": status(v.get("status")), "links": links(v)})
        if not rows:
            continue
        sns = sns_rows(metrics, cid)
        snsAt = max((d.get("collectedAt") or "")[:10] for d in metrics.values() if d.get("clientId") == cid) if sns else ""
        data = {"client": name, "updated": jst.strftime("%Y/%m/%d"), "today": jst.strftime("%Y-%m-%d"),
                "videos": rows, "sns": sns, "snsAt": snsAt.replace("-", "/")}
        blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        html = tpl.replace("__TITLE__", name + " 動画ライブラリ").replace("__DATA__", blob)
        path = os.path.join(out_dir, cid + ".html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        # same page with every month expanded, for pdf.py to print
        data["print"] = True
        blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        with open(os.path.join(out_dir, cid + ".print.html"), "w", encoding="utf-8") as fh:
            fh.write(tpl.replace("__TITLE__", name + " 動画ライブラリ").replace("__DATA__", blob))
        made.append((cid, name, len(rows), path))
    return made


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    for cid, name, n, path in build(sys.argv[1], sys.argv[2]):
        print("%s\t%s\t%d\t%s" % (cid, name, n, path))
