#!/usr/bin/env python3
"""Print each client's page to an A4 PDF with headless Chromium.

    python3 client-pages/pdf.py <out_dir> [clientId ...]

Reads <out_dir>/<clientId>.print.html written by build.py and writes
<out_dir>/<clientId>.pdf next to it. Links in the PDF stay clickable.
"""
import glob
import os
import shutil
import subprocess
import sys

CHROME = os.environ.get("CHROME") or shutil.which("chromium") or "/opt/pw-browsers/chromium"


def to_pdf(src, dst):
    subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=8000", "--print-to-pdf=" + dst, "file://" + os.path.abspath(src)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out, only = sys.argv[1], set(sys.argv[2:])
    for src in sorted(glob.glob(os.path.join(out, "*.print.html"))):
        cid = os.path.basename(src)[:-len(".print.html")]
        if only and cid not in only:
            continue
        dst = os.path.join(out, cid + ".pdf")
        to_pdf(src, dst)
        print("%s\t%s" % (cid, dst))
