#!/usr/bin/env python3
"""Monthly SNS stats collector for the 動画管理基盤 hub.

Reads the hub's client list (account URLs), runs Apify actors to fetch the
public numbers of each Instagram / TikTok / YouTube account (no login, no
official platform API), and writes one metrics document per client in the
shape the hub's `metrics` collection uses.

    APIFY_TOKEN=... python3 collector/collect.py clients.json --month 2026-09 --out metrics.json

clients.json: a list of {"id", "name", "ig", "tt", "yt", "active"} objects
(exactly what the hub stores under `clients`). Account fields may be full
URLs, "@handle" or bare handles.

Only standard-library modules are used so it runs anywhere Python 3.9+ does.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.apify.com/v2"
ACTORS = {
    "ig": "apify~instagram-profile-scraper",   # followers
    "igr": "apify~instagram-reel-scraper",     # per-reel play counts (the number shown on the Reel)
    "tt": "clockworks~tiktok-scraper",
    "yt": "streamers~youtube-scraper",
}


# ---------- account parsing ----------

def first_line(text, n=80):
    """First caption line with real content (skips lines like '・' or '◯')."""
    for line in (text or "").splitlines():
        t = line.strip()
        if len(re.sub(r"[\s・◯⚪︎○●◎\-_.。、|｜#]", "", t)) >= 3:
            return t[:n]
    return (text or "").strip()[:n]


def ig_user(v):
    v = (v or "").strip()
    m = re.search(r"instagram\.com/([A-Za-z0-9._]+)", v)
    u = m.group(1) if m else v.lstrip("@")
    return u if re.fullmatch(r"[A-Za-z0-9._]{1,30}", u or "") and u not in ("p", "reel", "explore") else None


def tt_user(v):
    v = (v or "").strip()
    m = re.search(r"tiktok\.com/@([A-Za-z0-9._]+)", v)
    u = m.group(1) if m else v.lstrip("@")
    return u if re.fullmatch(r"[A-Za-z0-9._]{2,24}", u or "") else None


def yt_handle(v):
    """'@handle' or 'channel/UC…' id from any channel URL form (/featured, /shorts, ?si=…), lower-cased."""
    v = (v or "").strip()
    m = re.search(r"youtube\.com/(@[A-Za-z0-9._-]+)", v) or re.search(r"youtube\.com/(channel/UC[A-Za-z0-9_-]+)", v)
    if m:
        return m.group(1).lower()
    if v and "/" not in v:
        return "@" + v.lstrip("@").lower()
    return None


def yt_url(v):
    """Canonical channel URL, so a pasted '/shorts' or '/featured' page does not change what is fetched."""
    h = yt_handle(v)
    return "https://www.youtube.com/" + h if h else None


# ---------- small helpers ----------

def num(*vals):
    """First value that is a real number (ints in strings accepted)."""
    for v in vals:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str) and re.fullmatch(r"\d+", v.replace(",", "")):
            return int(v.replace(",", ""))
    return None


def to_date(v):
    """ISO string / unix seconds -> 'YYYY-MM-DD' in JST, else None."""
    if v is None or v == "":
        return None
    jst = dt.timezone(dt.timedelta(hours=9))
    try:
        if isinstance(v, (int, float)):
            return dt.datetime.fromtimestamp(v, jst).strftime("%Y-%m-%d")
        s = str(v).replace("Z", "+00:00")
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo:
            d = d.astimezone(jst)
        return d.strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
        return m.group(1) if m else None


def prev_month(today=None):
    """Last month as YYYY-MM, judged in JST (the job runs early on the 1st, Japan time)."""
    t = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    first = t.replace(day=1)
    return (first - dt.timedelta(days=1)).strftime("%Y-%m")


# ---------- normalisers (one Apify item -> our shapes) ----------

def norm_ig(items, user, reels=None):
    """Followers from the profile scraper; videos from the reel scraper when it ran
    (its videoPlayCount matches the count Instagram shows), else from latestPosts."""
    prof = next((i for i in items if (i.get("username") or "").lower() == user.lower()), items[0] if items else None)
    if not prof and not reels:
        return None, []
    own = [r for r in (reels or []) if (r.get("ownerUsername") or user).lower() == user.lower()]
    vids = []
    for p in own or (prof or {}).get("latestPosts") or []:
        is_video = (p.get("type") or p.get("mediaType") or "").lower() in ("video", "reel", "clips") or p.get("videoViewCount") is not None or p.get("videoPlayCount") is not None
        if not is_video:
            continue
        vids.append({
            "platform": "ig",
            "title": first_line(p.get("caption")),
            "url": p.get("url") or ("https://www.instagram.com/p/%s/" % p["shortCode"] if p.get("shortCode") else ""),
            "date": to_date(p.get("timestamp")),
            "views": num(p.get("videoPlayCount"), p.get("videoViewCount")),
            "likes": num(p.get("likesCount")),
            "comments": num(p.get("commentsCount")),
        })
    return {"followers": num((prof or {}).get("followersCount"))}, vids


def norm_tt(items, user):
    followers = None
    vids = []
    for it in items:
        a = it.get("authorMeta") or {}
        if (a.get("name") or user).lower() != user.lower():
            continue
        followers = num(a.get("fans"), followers)
        if not it.get("webVideoUrl") and not it.get("id"):
            continue
        vids.append({
            "platform": "tt",
            "title": first_line(it.get("text")),
            "url": it.get("webVideoUrl") or "",
            "date": to_date(it.get("createTimeISO") or it.get("createTime")),
            "views": num(it.get("playCount")),
            "likes": num(it.get("diggCount")),
            "comments": num(it.get("commentCount")),
            "shares": num(it.get("shareCount")),
            "saves": num(it.get("collectCount")),
        })
    return {"followers": followers}, vids


def is_short(it):
    """YouTube Shorts: /shorts/ URL, a 'shorts' type, or a duration of 3 minutes or less."""
    if "/shorts/" in (it.get("url") or "") or str(it.get("type") or "").lower().startswith("short"):
        return True
    d = it.get("duration")
    if isinstance(d, str) and re.fullmatch(r"\d{1,2}(:\d{2}){1,2}", d):
        parts = [int(x) for x in d.split(":")]
        secs = parts[-1] + 60 * parts[-2] + (3600 * parts[0] if len(parts) == 3 else 0)
        return secs <= 180
    return False


def norm_yt(items):
    followers = None
    vids = []
    for it in items:
        followers = num(it.get("numberOfSubscribers"), followers)
        if not it.get("url"):
            continue
        vids.append({
            "platform": "yt",
            "kind": "short" if is_short(it) else "long",
            "title": (it.get("title") or "").strip()[:80],
            "url": it.get("url"),
            "date": to_date(it.get("date") or it.get("uploadDate")),
            "views": num(it.get("viewCount")),
            "likes": num(it.get("likes")),
            "comments": num(it.get("commentsCount")),
        })
    return {"followers": followers}, vids


def monthly(profile, vids, month, extra=()):
    """Platform block for the hub: followers now + totals of videos posted in `month`."""
    inm = [v for v in vids if (v.get("date") or "").startswith(month)]
    out = {}
    if profile and profile.get("followers") is not None:
        out["followers"] = profile["followers"]
    out["posts"] = len(inm)
    for k in ("views", "likes", "comments") + tuple(extra):
        vals = [v[k] for v in inm if v.get(k) is not None]
        if vals:
            out[k] = sum(vals)
    return out, inm


# ---------- Apify calls ----------

def call(method, path, token, body=None, timeout=90):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers=dict({"Content-Type": "application/json"}, **({"Authorization": "Bearer " + token} if token else {})))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "null")


def run_actor(actor, inp, token, max_wait=1800):
    run = call("POST", "/acts/%s/runs" % actor, token, inp)["data"]
    waited = 0
    while run["status"] in ("READY", "RUNNING") and waited < max_wait:
        run = call("GET", "/actor-runs/%s?waitForFinish=60" % run["id"], token, timeout=90)["data"]
        waited += 60
    if run["status"] != "SUCCEEDED":
        raise RuntimeError("%s ended with status %s" % (actor, run["status"]))
    return call("GET", "/datasets/%s/items?clean=true&format=json" % run["defaultDatasetId"], token, timeout=120) or []


# ---------- main ----------

def collect(clients, month, token, log=print):
    clients = [c for c in clients if c.get("active", True) is not False]
    ig = {c["id"]: ig_user(c.get("ig")) for c in clients}
    tt = {c["id"]: tt_user(c.get("tt")) for c in clients}
    yt = {c["id"]: yt_url(c.get("yt")) for c in clients}
    raw = {"ig": [], "igr": [], "tt": [], "yt": []}
    errors = []

    def attempt(p, fn):
        try:
            raw[p] = fn()
            log("%s: %d items" % (p, len(raw[p])))
        except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as e:
            errors.append("%s: %s" % (p, e))
            log("%s FAILED: %s" % (p, e))

    users = sorted({u for u in ig.values() if u})
    if users:
        attempt("ig", lambda: run_actor(ACTORS["ig"], {"usernames": users}, token))
        attempt("igr", lambda: run_actor(ACTORS["igr"], {"username": users, "resultsLimit": 40}, token))
    users = sorted({u for u in tt.values() if u})
    if users:
        attempt("tt", lambda: run_actor(ACTORS["tt"], {"profiles": users, "resultsPerPage": 40,
                                                      "shouldDownloadVideos": False, "shouldDownloadCovers": False,
                                                      "shouldDownloadSubtitles": False, "shouldDownloadSlideshowImages": False}, token))
    urls = sorted({u for u in yt.values() if u})
    if urls:
        attempt("yt", lambda: run_actor(ACTORS["yt"], {"startUrls": [{"url": u} for u in urls], "maxResults": 30,
                                                      "maxResultsShorts": 30, "maxResultStreams": 0}, token))

    def yt_items_for(url):
        """Only the items whose channel is this client's channel (never a fallback to everything)."""
        h = yt_handle(url)
        out = []
        for i in raw["yt"]:
            cands = {yt_handle(i.get(k) or "") for k in ("channelUrl", "inputChannelUrl", "fromYTUrl", "input")}
            un = (i.get("channelUsername") or "").lower().lstrip("@")
            if h in cands or (un and h == "@" + un):
                out.append(i)
        return out

    docs = []
    for c in clients:
        doc = {"clientId": c["id"], "month": month, "videos": [], "source": "apify",
               "collectedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if ig[c["id"]] and (raw["ig"] or raw["igr"]):
            prof, vids = norm_ig(raw["ig"], ig[c["id"]], raw["igr"])
            doc["ig"], inm = monthly(prof, vids, month)
            doc["videos"] += inm
        if tt[c["id"]] and raw["tt"]:
            prof, vids = norm_tt(raw["tt"], tt[c["id"]])
            doc["tt"], inm = monthly(prof, vids, month, extra=("shares", "saves"))
            doc["videos"] += inm
        if yt[c["id"]] and raw["yt"]:
            items = yt_items_for(yt[c["id"]])
            prof, vids = norm_yt(items)
            doc["yt"], inm = monthly(prof, vids, month)
            doc["videos"] += inm
        if any(k in doc for k in ("ig", "tt", "yt")):
            docs.append({"docId": "%s_%s" % (c["id"], month), "data": doc})
    return docs, errors


def this_month(today=None):
    """Current month as YYYY-MM in JST."""
    t = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    return t.strftime("%Y-%m")


def collect_months(clients, months, token, log=print):
    """Run the actors once and build docs for every month in `months`."""
    global run_actor
    real, cache = run_actor, {}

    def cached(actor, inp, tok, **kw):
        if actor not in cache:
            cache[actor] = real(actor, inp, tok, **kw)
        return cache[actor]

    run_actor = cached
    try:
        docs, errors = [], []
        for m in months:
            d, e = collect(clients, m, token, log=log)
            docs += d
            errors += [x for x in e if x not in errors]
        return docs, errors
    finally:
        run_actor = real


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clients", help="clients JSON exported from the hub")
    ap.add_argument("--month", default=prev_month(),
                    help="target month(s) YYYY-MM, comma separated; 'now' = this month and last month (default: last month)")
    ap.add_argument("--out", default="metrics.json")
    ap.add_argument("--only", default="all", help="comma separated client ids to fetch (default: all)")
    a = ap.parse_args()
    months = [prev_month(), this_month()] if a.month == "now" else [m.strip() for m in a.month.split(",") if m.strip()]
    # The token may come from APIFY_TOKEN, or be injected by the environment's
    # "API認証情報" (credential proxy) for api.apify.com, in which case it is empty here.
    token = os.environ.get("APIFY_TOKEN", "")
    with open(a.clients, encoding="utf-8") as f:
        clients = json.load(f)
    if a.only != "all":
        wanted = {x.strip() for x in a.only.split(",") if x.strip()}
        clients = [c for c in clients if c.get("id") in wanted]
    docs, errors = collect_months(clients, months, token, log=lambda s: print(s, file=sys.stderr))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"months": months, "docs": docs, "errors": errors}, f, ensure_ascii=False, indent=1)
    print("wrote %d docs to %s (%d errors)" % (len(docs), a.out, len(errors)), file=sys.stderr)


if __name__ == "__main__":
    main()
