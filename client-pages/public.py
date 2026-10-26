#!/usr/bin/env python3
"""Turn build.py's per-client pages into a public static site (GitHub Pages).

    python3 client-pages/public.py <dump_dir> <out_dir> <site_dir>

Each client gets https://<owner>.github.io/<repo>/v/<slug>/ where <slug> is a
random, hard-to-guess string kept in the hub as clients/<id>.publicSlug, so a
client's link never changes between refreshes. Clients without a slug get a new
one; the new slugs are printed as JSON so they can be written back to the hub.
It also writes l/<name>.csv (No, name, link, video count, updated) for the
management spreadsheet, which reads it with IMPORTDATA. "No" is clients/<id>.publicNo:
fixed per client, new clients get the next number (newNos, to write back).
Pages carry noindex and the site has a robots.txt, so search engines skip them.
Anyone who has a page's link can open it without logging in.
"""
import csv
import datetime
import glob
import json
import os
import re
import secrets
import shutil
import sys

# Fixed, hard-to-guess name of the list the management spreadsheet imports (IMPORTDATA).
LIST_CSV = "l/a8Qm3vTzK7pWn2Rx.csv"
HEAD = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<meta name="robots" content="noindex,nofollow,noarchive">'
        '<meta name="referrer" content="no-referrer">'
        '<style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>'
        '</head><body>\n')
base_url = "https://motoharudayon0614-ctrl.github.io/my-project/"
TAIL = '\n</body></html>\n'


def main(dump, out_dir, site):
    clients = {}
    for f in glob.glob(os.path.join(dump, "clients", "*.json")):
        clients[os.path.basename(f)[:-5]] = json.load(open(f, encoding="utf-8"))
    if os.path.isdir(os.path.join(site, "v")):
        shutil.rmtree(os.path.join(site, "v"))  # rebuilt from scratch: removed clients disappear
    os.makedirs(site, exist_ok=True)
    new, pages = {}, []
    nos = {cid: c["publicNo"] for cid, c in clients.items() if isinstance(c.get("publicNo"), int)}
    new_nos = {}
    for f in sorted(glob.glob(os.path.join(out_dir, "*.html"))):
        cid = os.path.basename(f)[:-5]
        if cid.endswith(".print") or cid not in clients:
            continue
        slug = clients[cid].get("publicSlug") or new.setdefault(cid, secrets.token_urlsafe(12).replace("_", "x").replace("-", "y"))
        d = os.path.join(site, "v", slug)
        os.makedirs(d, exist_ok=True)
        with open(f, encoding="utf-8") as fh, open(os.path.join(d, "index.html"), "w", encoding="utf-8") as oh:
            oh.write(HEAD + fh.read() + TAIL)
        no = nos.get(cid)
        if no is None:  # new client: next number, so rows in the spreadsheet never shift
            no = max(list(nos.values()) + [0]) + 1
            nos[cid] = new_nos[cid] = no
        n = len(json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', open(f, encoding="utf-8").read(), re.S).group(1).replace("<\\/", "</"))["videos"])
        pages.append({"id": cid, "name": clients[cid].get("name"), "slug": slug, "no": no, "videos": n})
    pages.sort(key=lambda p: p["no"])
    os.makedirs(os.path.join(site, "l"), exist_ok=True)
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y/%m/%d %H:%M")
    with open(os.path.join(site, LIST_CSV), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["No", "会社名", "公開リンク", "動画本数", "更新日時"])
        for p in pages:
            w.writerow([p["no"], p["name"], base_url + "v/" + p["slug"] + "/", p["videos"], today])
    with open(os.path.join(site, "robots.txt"), "w") as fh:
        fh.write("User-agent: *\nDisallow: /\n")
    with open(os.path.join(site, "index.html"), "w") as fh:  # no directory listing of clients
        fh.write(HEAD + "<p></p>" + TAIL)
    open(os.path.join(site, ".nojekyll"), "w").close()
    print(json.dumps({"pages": pages, "newSlugs": new, "newNos": new_nos}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
