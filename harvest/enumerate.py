#!/usr/bin/env python3
"""Query the Wayback CDX API for every archived Bawarchi contribution recipe page,
keep the most recent HTTP 200 snapshot of each, and write a work-list TSV."""
import re
import sys
import urllib.request
import pathlib
from collections import defaultdict

CDX = ("http://web.archive.org/cdx/search/cdx?"
       "url=bawarchi.com/contribution*&output=text"
       "&fl=original,timestamp,statuscode&collapse=digest&limit=200000")
OUT = pathlib.Path(__file__).parent / "worklist.tsv"
RECIPE_RE = re.compile(r"/contribution/(contrib\d+\.html)$", re.IGNORECASE)

def main():
    print(f"Querying CDX: {CDX}", file=sys.stderr)
    with urllib.request.urlopen(CDX, timeout=180) as r:
        rows = r.read().decode("utf-8", "replace").splitlines()
    print(f"CDX returned {len(rows)} rows", file=sys.stderr)

    # filename -> (best_timestamp, original_url) keeping the newest 200 capture
    best = {}
    for line in rows:
        parts = line.split()
        if len(parts) < 3:
            continue
        original, timestamp, status = parts[0], parts[1], parts[2]
        m = RECIPE_RE.search(original)
        if not m or status != "200":
            continue
        fname = m.group(1).lower()
        cur = best.get(fname)
        if cur is None or timestamp > cur[0]:
            best[fname] = (timestamp, original)

    with open(OUT, "w") as fh:
        fh.write("file\ttimestamp\toriginal\n")
        for fname in sorted(best, key=lambda f: int(re.search(r"\d+", f).group())):
            ts, orig = best[fname]
            fh.write(f"{fname}\t{ts}\t{orig}\n")
    print(f"Wrote {len(best)} recipes to {OUT}", file=sys.stderr)

if __name__ == "__main__":
    main()
