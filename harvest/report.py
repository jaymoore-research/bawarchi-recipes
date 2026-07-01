#!/usr/bin/env python3
"""Report harvest completeness: worklist vs what's actually on disk."""
import re
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
worklist = (ROOT / "harvest" / "worklist.tsv").read_text().splitlines()[1:]
wanted = {ln.split("\t")[0] for ln in worklist if ln.strip()}
have = {p.name.lower() for p in (ROOT / "contribution").glob("contrib*.html")
        if p.stat().st_size > 200}
missing = sorted(wanted - have, key=lambda f: int(re.search(r"\d+", f).group()))

print(f"wanted (work-list): {len(wanted)}")
print(f"have on disk (>200B): {len(have)}")
print(f"recovered coverage:   {len(wanted & have) / len(wanted) * 100:.1f}%")
print(f"still missing:        {len(missing)}")
if missing:
    print("missing sample:", missing[:15])
    (ROOT / "harvest" / "still-missing.txt").write_text("\n".join(missing) + "\n")
    print("full list -> harvest/still-missing.txt")
