#!/usr/bin/env python3
"""学びの「次に探す条件」から、YouTube・Instagram・TikTok の参考動画の候補を集める。

    python3 pdca/search.py plan.json --out found.json [--months 3] [--min-views 100000] [--limit 20] [--allow-ads]

plan.json は学びごとの検索語のリスト（Claude が学びの queries から作る）:
    [{"learningId": "lr_xxx_01", "yt": ["自宅サウナ 後悔"], "tt": ["自宅サウナ"], "ig": ["自宅サウナ"],
      "exclude": ["クライアントのアカウント名"]}]
  - yt: YouTube の検索語（ログイン不要の検索ページから取る。取れない環境では Apify streamers~youtube-scraper の検索）
  - tt: TikTok の検索語（Apify clockworks~tiktok-scraper の検索）
  - ig: Instagram のハッシュタグ（# なし。Apify apify~instagram-hashtag-scraper のリール）
  - exclude: 除くアカウント（部分一致。自社・クライアント自身など）

出力は {"items": [...], "errors": [...]}。items は再生数の多い順で、
url, platform(ig/tt/yts/ytl), title, account, views, likes, comments, postedAt, age_days, query, learningId。
広告・タイアップ・商品リンク付き・アフィリエイトらしいもの（ad=True）は、--allow-ads を付けない限り除く。
Apify のトークンは APIFY_TOKEN か、環境の「API認証情報」（api.apify.com へ自動で付く）から。
"""
import argparse, datetime as dt, json, os, re, subprocess, sys, time, unicodedata, urllib.parse, urllib.request

API = "https://api.apify.com/v2"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
YEAR = "EgIIBQ%3D%3D"  # YouTube の期間フィルタ「今年」
NOW = dt.datetime.now(dt.timezone.utc)


def norm(s):
    return unicodedata.normalize("NFKC", s or "").lower()


def relevant(title, q):
    """検索語のどれか（2文字以上）がタイトルに入っているものだけ残す（混ざる広告・ドラマを落とす）。"""
    words = [w for w in norm(q).replace("#", " ").split() if len(w) >= 2]
    return not words or any(w in norm(title) for w in words)


AD_TEXT = re.compile(r"[#＃]\s*(pr|ad|sponsored|プロモーション|タイアップ)\b|有償の?パートナーシップ|タイアップ|案件|提供[:：]|tiktok\s*shop|tiktokショップ|"
                     r"プロフィール欄?の?リンク|購入はこちら|商品リンク|リンクから(購入|検索)|クーポンコード|楽天room|amazon(で|の)", re.I)
AD_KEYS = ("isAd", "isSponsored", "isPaidPartnership", "paidPartnership", "adAuthorization", "brandOrganicType",
           "adLabelVersion", "isECVideo", "sponsors", "anchors")


def is_ad(raw, text):
    """広告・タイアップ・商品リンク付き・アフィリエイトらしいものを見分ける（フラグとキャプションの両方で）。"""
    for k in AD_KEYS:
        v = raw.get(k) if isinstance(raw, dict) else None
        if v not in (None, False, 0, "", [], {}):
            return True
    return bool(AD_TEXT.search(unicodedata.normalize("NFKC", text or "")))


def age_of(iso):
    try:
        t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (NOW - (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc))).days
    except ValueError:
        return None


# ---------- YouTube（検索ページ） ----------

def yt_views(text):
    t = (text or "").replace(",", "").replace("回視聴", "").replace(" ", "")
    m = re.match(r"([\d.]+)(万|億)?", t)
    return int(float(m.group(1)) * {"万": 10_000, "億": 100_000_000}.get(m.group(2), 1)) if m else None


def yt_age(text):
    m = re.match(r"(\d+)\s*(秒|分|時間|日|週間|か月|ヶ月|年)", text or "")
    return int(m.group(1)) * {"秒": 0, "分": 0, "時間": 0, "日": 1, "週間": 7, "か月": 30, "ヶ月": 30, "年": 365}[m.group(2)] if m else None


def youtube(q):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(q) + "&sp=" + YEAR + "&hl=ja&gl=JP"
    html = subprocess.run(["curl", "-s", "-m", "30", "-A", UA, "-H", "Accept-Language: ja-JP,ja;q=0.9", url],
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    out = []

    def walk(o):
        if isinstance(o, dict):
            if "videoRenderer" in o:
                v = o["videoRenderer"]
                ago = (v.get("publishedTimeText") or {}).get("simpleText")
                out.append({"url": "https://www.youtube.com/watch?v=" + v.get("videoId", ""), "platform": "ytl",
                            "title": "".join(r.get("text", "") for r in (v.get("title") or {}).get("runs", [])),
                            "account": ((v.get("ownerText") or {}).get("runs") or [{}])[0].get("text"),
                            "views": yt_views((v.get("viewCountText") or {}).get("simpleText")),
                            "postedAt": ago, "age_days": yt_age(ago)})
            if "shortsLockupViewModel" in o:
                s = o["shortsLockupViewModel"]
                md = s.get("overlayMetadata") or {}
                vid = (((s.get("onTap") or {}).get("innertubeCommand") or {}).get("reelWatchEndpoint") or {}).get("videoId", "")
                out.append({"url": "https://www.youtube.com/shorts/" + vid, "platform": "yts",
                            "title": (md.get("primaryText") or {}).get("content"), "account": None,
                            "views": yt_views((md.get("secondaryText") or {}).get("content")), "postedAt": None, "age_days": None})
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    if m:
        walk(json.loads(m.group(1)))
    return [r for r in out if not r["url"].endswith(("=", "/"))]


# ---------- Apify（Instagram・TikTok） ----------

def youtube_apify(queries, limit):
    """検索ページが開けない環境（クラウドなど）用。Apify で同じ検索をする。"""
    items = run_actor("streamers~youtube-scraper", {"searchQueries": queries, "maxResults": limit,
                                                    "maxResultsShorts": limit, "maxResultStreams": 0})
    out = []
    for v in items:
        url = first(v, "url")
        if not url:
            continue
        posted = first(v, "date", "uploadDate")
        short = "/shorts/" in url or str(first(v, "type") or "").lower() in ("shorts", "short")
        out.append({"url": url, "platform": "yts" if short else "ytl", "title": first(v, "title") or "",
                    "account": first(v, "channelName"), "views": first(v, "viewCount"),
                    "likes": first(v, "likes"), "comments": first(v, "commentsCount"),
                    "postedAt": posted, "age_days": age_of(posted) if posted else None,
                    "query": first(v, "input", "searchQuery")})
    return out


def call(method, path, body=None, timeout=90):
    token = os.environ.get("APIFY_TOKEN", "")
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers=dict({"Content-Type": "application/json"}, **({"Authorization": "Bearer " + token} if token else {})))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "null")


def run_actor(actor, inp, max_wait=1200):
    run = call("POST", "/acts/%s/runs" % actor, inp)["data"]
    waited = 0
    while run["status"] in ("READY", "RUNNING") and waited < max_wait:
        run = call("GET", "/actor-runs/%s?waitForFinish=60" % run["id"])["data"]
        waited += 60
    if run["status"] != "SUCCEEDED":
        raise RuntimeError("%s が %s で終わりました" % (actor, run["status"]))
    return call("GET", "/datasets/%s/items?clean=true&format=json" % run["defaultDatasetId"], timeout=120) or []


def first(d, *keys):
    for k in keys:
        cur = d
        for part in k.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur not in (None, ""):
            return cur
    return None


def tiktok(queries, limit):
    items = run_actor("clockworks~tiktok-scraper", {
        "searchQueries": queries, "resultsPerPage": limit, "searchSection": "/video",
        "shouldDownloadVideos": False, "shouldDownloadCovers": False,
        "shouldDownloadSubtitles": False, "shouldDownloadSlideshowImages": False})
    out = []
    for v in items:
        url = first(v, "webVideoUrl", "url")
        if not url:
            continue
        posted = first(v, "createTimeISO") or (dt.datetime.fromtimestamp(v["createTime"], dt.timezone.utc).isoformat()
                                               if isinstance(v.get("createTime"), (int, float)) else None)
        out.append({"url": url, "platform": "tt", "title": (first(v, "text") or "")[:120],
                    "account": first(v, "authorMeta.name", "authorMeta.nickName"),
                    "views": first(v, "playCount"), "likes": first(v, "diggCount"), "comments": first(v, "commentCount"),
                    "postedAt": posted, "age_days": age_of(posted) if posted else None,
                    "query": first(v, "searchQuery", "input"), "ad": is_ad(v, first(v, "text"))})
    return out


def instagram(tags, limit):
    items = run_actor("apify~instagram-hashtag-scraper", {
        "hashtags": [t.lstrip("#") for t in tags], "resultsType": "reels", "resultsLimit": limit})
    out = []
    for v in items:
        url = first(v, "url")
        if not url or (v.get("type") and v["type"] not in ("Video", "Reel", "Clip")):
            continue
        posted = first(v, "timestamp")
        out.append({"url": url, "platform": "ig", "title": (first(v, "caption") or "")[:120],
                    "account": first(v, "ownerUsername", "ownerFullName"),
                    "views": first(v, "videoPlayCount", "videoViewCount", "playsCount"),
                    "likes": first(v, "likesCount"), "comments": first(v, "commentsCount"),
                    "postedAt": posted, "age_days": age_of(posted) if posted else None,
                    "query": urllib.parse.unquote(src.rstrip("/").split("/")[-1]) if (src := first(v, "inputUrl", "hashtag")) else None,
                    "ad": is_ad(v, first(v, "caption"))})
    return out


def owner_of(item, plan, key):
    """Apify は検索語をまとめて1回で取るので、結果がどの学びの検索語から来たかを当てる。"""
    q = norm(item.get("query") or "").lstrip("#")
    for p in plan:
        if any(norm(x).lstrip("#") == q for x in p.get(key) or []):
            return p
    for p in plan:  # 当たらなければ、キャプションに検索語が入っている学び
        if any(relevant(item["title"], x) for x in p.get(key) or []):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--out", default="found.json")
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--min-views", type=int, default=100000)
    ap.add_argument("--allow-ads", action="store_true", help="広告・タイアップ・アフィリエイトらしい動画も残す")
    ap.add_argument("--limit", type=int, default=20, help="Instagram・TikTok の検索語1つあたりの取得数（Apify の料金に効く）")
    ap.add_argument("--apify", default="ig", help="Apify（有料）を使う媒体をカンマ区切りで（yt,tt,ig）。既定は Instagram だけ")
    a = ap.parse_args()
    paid = {x.strip() for x in a.apify.split(",") if x.strip()}
    plan = json.load(open(a.plan, encoding="utf-8"))
    rows, errors = [], []

    yt_failed = []
    for p in plan:
        for q in p.get("yt") or []:
            try:
                for r in youtube(q):
                    if relevant(r["title"], q):
                        rows.append(dict(r, query=q, learningId=p["learningId"]))
            except Exception:  # 検索ページが開けないときは、あとで Apify でまとめて探す
                yt_failed.append(q)
        time.sleep(1)
    if yt_failed and "yt" not in paid:
        errors.append("YouTube：検索ページが開けず、Apify（有料）は使わない設定のため %d 語を飛ばしました" % len(yt_failed))
    elif yt_failed:
        try:
            found = youtube_apify(yt_failed, a.limit)
            print("yt(Apify): %d件" % len(found), file=sys.stderr)
            for r in found:
                p = owner_of(r, plan, "yt")
                if p and relevant(r["title"], r.get("query") or " ".join(p.get("yt") or [])):
                    rows.append(dict(r, query=r.get("query") or "", learningId=p["learningId"]))
        except Exception as e:
            errors.append("YouTube（検索ページもApifyも失敗）：%s" % e)

    for key, fn in (("tt", tiktok), ("ig", instagram)):
        terms = sorted({x for p in plan for x in p.get(key) or []})
        if not terms:
            continue
        if key not in paid:
            errors.append("%s：Apify（有料）は使わない設定のため飛ばしました" % ("TikTok" if key == "tt" else "Instagram"))
            continue
        try:
            found = fn(terms, a.limit)
            print("%s: %d件" % (key, len(found)), file=sys.stderr)
        except Exception as e:
            errors.append("%s：%s" % ("TikTok" if key == "tt" else "Instagram", e))
            continue
        for r in found:
            p = owner_of(r, plan, key)
            if p:
                rows.append(dict(r, query=r.get("query") or "", learningId=p["learningId"]))

    excl = {p["learningId"]: [norm(x) for x in p.get("exclude") or [] if x] for p in plan}
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: -(r.get("views") or 0)):
        if r["url"] in seen or (r.get("views") or 0) < a.min_views:
            continue
        if not a.allow_ads and (r.get("ad") or is_ad({}, r.get("title"))):
            continue
        if r.get("age_days") is not None and r["age_days"] > 30 * a.months:
            continue
        if any(x in norm(r.get("account")) for x in excl.get(r["learningId"], [])):
            continue
        seen.add(r["url"])
        out.append(r)
    json.dump({"items": out, "errors": errors}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("%d件を %s に書きました（エラー %d）" % (len(out), a.out, len(errors)), file=sys.stderr)
    for e in errors:
        print("  " + e, file=sys.stderr)


if __name__ == "__main__":
    main()
