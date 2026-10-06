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
    "ig": "apify~instagram-profile-scraper",
    "tt": "clockworks~tiktok-scraper",
    "yt": "streamers~youtube-scraper",
}


# ---------- account parsing ----------

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


def yt_url(v):
    v = (v or "").strip()
    if not v:
        return None
    if "youtube.com/" in v or "youtu.be/" in v:
        return v if v.startswith("http") else "https://" + v
    return "https://www.youtube.com/@" + v.lstrip("@")


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

def norm_ig(items, user):
    prof = next((i for i in items if (i.get("username") or "").lower() == user.lower()), items[0] if items else None)
    if not prof:
        return None, []
    vids = []
    for p in prof.get("latestPosts") or []:
        is_video = (p.get("type") or p.get("mediaType") or "").lower() in ("video", "reel", "clips") or p.get("videoViewCount") is not None or p.get("videoPlayCount") is not None
        if not is_video:
            continue
        vids.append({
            "platform": "ig",
            "title": (p.get("caption") or "").strip().split("\n")[0][:80],
            "url": p.get("url") or ("https://www.instagram.com/p/%s/" % p["shortCode"] if p.get("shortCode") else ""),
            "date": to_date(p.get("timestamp")),
            "views": num(p.get("videoPlayCount"), p.get("videoViewCount")),
            "likes": num(p.get("likesCount")),
            "comments": num(p.get("commentsCount")),
        })
    return {"followers": num(prof.get("followersCount"))}, vids


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
            "title": (it.get("text") or "").strip().split("\n")[0][:80],
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
    raw = {"ig": [], "tt": [], "yt": []}
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
        key = url.rstrip("/").split("/")[-1].lower()
        return [i for i in raw["yt"] if key in json.dumps([i.get("channelUrl"), i.get("inputChannelUrl"), i.get("input"),
                                                          i.get("channelUsername"), i.get("fromYTUrl")]).lower()]

    docs = []
    for c in clients:
        doc = {"clientId": c["id"], "month": month, "videos": [], "source": "apify",
               "collectedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if ig[c["id"]] and raw["ig"]:
            prof, vids = norm_ig(raw["ig"], ig[c["id"]])
            doc["ig"], inm = monthly(prof, vids, month)
            doc["videos"] += inm
        if tt[c["id"]] and raw["tt"]:
            prof, vids = norm_tt(raw["tt"], tt[c["id"]])
            doc["tt"], inm = monthly(prof, vids, month, extra=("shares", "saves"))
            doc["videos"] += inm
        if yt[c["id"]] and raw["yt"]:
            items = yt_items_for(yt[c["id"]]) if len({u for u in yt.values() if u}) > 1 else raw["yt"]
            prof, vids = norm_yt(items)
            doc["yt"], inm = monthly(prof, vids, month)
            doc["videos"] += inm
        if any(k in doc for k in ("ig", "tt", "yt")):
            docs.append({"docId": "%s_%s" % (c["id"], month), "data": doc})
    return docs, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clients", help="clients JSON exported from the hub")
    ap.add_argument("--month", default=prev_month(), help="target month YYYY-MM (default: last month)")
    ap.add_argument("--out", default="metrics.json")
    a = ap.parse_args()
    # The token may come from APIFY_TOKEN, or be injected by the environment's
    # "API認証情報" (credential proxy) for api.apify.com, in which case it is empty here.
    token = os.environ.get("APIFY_TOKEN", "")
    with open(a.clients, encoding="utf-8") as f:
        clients = json.load(f)
    docs, errors = collect(clients, a.month, token, log=lambda s: print(s, file=sys.stderr))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"month": a.month, "docs": docs, "errors": errors}, f, ensure_ascii=False, indent=1)
    print("wrote %d docs to %s (%d errors)" % (len(docs), a.out, len(errors)), file=sys.stderr)


if __name__ == "__main__":
    main()
