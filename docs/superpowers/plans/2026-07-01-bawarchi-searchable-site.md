# Bawarchi Searchable Recipe Site — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover the full Bawarchi readers'-contributions recipe archive from the Wayback Machine (~3,735 → ~5,920 recipes), then build and deploy a hosted, searchable single-page website of every recipe.

**Architecture:** Phase 1 harvests missing recipe pages from `web.archive.org` into `contribution/`. Phase 2 parses those static HTML pages into a single `recipes.json`. Phase 3 is a static single-page app (`index.html` + `app.js` + `styles.css` + `recipes.json`) with client-side search. Phase 4 deploys to GitHub Pages.

**Tech Stack:** Python 3 (stdlib only — `re`, `json`, `pathlib`, `html`, `urllib`) run via `uv`; `curl` for downloads; `pytest` for the parser test; vanilla HTML/CSS/JS (no framework, no build step).

**Working directory:** `~/Documents/projects/bawarchi` (already a git repo). All paths below are relative to it unless absolute.

---

## File Structure

- Create: `harvest/enumerate.py` — query CDX API → `harvest/worklist.tsv` (recipe filename + best snapshot timestamp + original URL).
- Create: `harvest/fetch.sh` — resumable, rate-limited downloader of missing recipes from Wayback into `contribution/`.
- Create: `harvest/refresh_categories.sh` — pull latest snapshot of each category index page into `contribution/`.
- Create: `build_site.py` — parse `contribution/*.html` → `site/recipes.json` + print build stats.
- Create: `tests/test_parser.py` — parser unit test against a known recipe.
- Create: `site/index.html`, `site/app.js`, `site/styles.css` — the single-page app. `site/recipes.json` is generated.
- Reference (do not modify): `build-book.py` — reuse its `CATEGORY_ORDER`, `NONVEG_CATS`, `VEG_SUBCATS_BY_SPECIFICITY`, and the cleanup regexes in `extract_recipe`.

**Category slugs** (from `build-book.py`, plus non-veg + `microwave`):
`vegetables, paneer, soya, daal, curries, rice, roti, dosas, bread, regional, east, snacks, pakora, chutney, raita, salad, soup, refreshment, sweets, cakes, mushroom, assorted, microwave` and non-veg `chicken, redmeat, seafood, egg, nonvegsweets`. `south` is a cross-cutting tag, not a primary category.

---

# Phase 1 — Wayback Harvest

### Task 1: Enumerate the master recipe list from the CDX API

**Files:**
- Create: `harvest/enumerate.py`
- Output: `harvest/worklist.tsv`

- [ ] **Step 1: Write `harvest/enumerate.py`**

```python
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
```

- [ ] **Step 2: Run it**

Run: `cd ~/Documents/projects/bawarchi && uv run python harvest/enumerate.py`
Expected: stderr reports "Wrote ~5900 recipes to …/worklist.tsv" (a few hundred either way is fine).

- [ ] **Step 3: Sanity-check the output**

Run: `head -3 harvest/worklist.tsv && wc -l harvest/worklist.tsv && awk -F'\t' 'NR>1{print substr($2,1,4)}' harvest/worklist.tsv | sort | uniq -c`
Expected: 3 columns; ~5,900 data rows; a spread of snapshot years (not all 2001), confirming later captures were selected.

- [ ] **Step 4: Commit**

```bash
git add harvest/enumerate.py harvest/worklist.tsv
git commit -m "harvest: enumerate master recipe list from Wayback CDX"
```

---

### Task 2: Resumable downloader for missing recipes

**Files:**
- Create: `harvest/fetch.sh`
- Modifies (data): `contribution/contrib*.html`, appends `harvest/fetch-manifest.tsv`

- [ ] **Step 1: Write `harvest/fetch.sh`**

```bash
#!/bin/bash
# Download recipe pages listed in harvest/worklist.tsv from the Wayback Machine.
# Resumable: skips files already present (>200 bytes). Rate-limited, retrying.
# Uses the "id_" raw-content suffix to get original HTML without the WB toolbar.
set -u
cd "$(dirname "$0")/.."               # project root
WORKLIST="harvest/worklist.tsv"
DEST="contribution"
MANIFEST="harvest/fetch-manifest.tsv"

[ -f "$MANIFEST" ] || echo -e "file\thttp\tsize\tattempts" > "$MANIFEST"

total=$(($(wc -l < "$WORKLIST") - 1)); i=0; got=0; skip=0; fail=0
# Skip header (NR>1)
while IFS=$'\t' read -r fname ts orig; do
  [ "$fname" = "file" ] && continue
  i=$((i+1))
  if [ -f "$DEST/$fname" ] && [ "$(wc -c < "$DEST/$fname")" -gt 200 ]; then
    skip=$((skip+1)); continue
  fi
  url="https://web.archive.org/web/${ts}id_/${orig}"
  code=000; size=0; a=0
  for a in 1 2 3; do
    code=$(curl -sL "$url" -o "$DEST/$fname" -w "%{http_code}" --max-time 45 2>/dev/null || echo 000)
    size=$(wc -c < "$DEST/$fname" 2>/dev/null || echo 0)
    [ "$code" = "200" ] && [ "$size" -gt 200 ] && break
    sleep $((a * 3))
  done
  if [ "$code" = "200" ] && [ "$size" -gt 200 ]; then
    got=$((got+1))
  else
    fail=$((fail+1)); rm -f "$DEST/$fname"
  fi
  echo -e "$fname\t$code\t$size\t$a" >> "$MANIFEST"
  [ $((i % 100)) -eq 0 ] && echo "[$i/$total] got=$got skip=$skip fail=$fail last=$fname ($code)"
  sleep 0.8
done < "$WORKLIST"
echo "DONE: total=$total got=$got skip=$skip fail=$fail"
```

- [ ] **Step 2: Make executable and dry-check the skip logic**

Run: `chmod +x harvest/fetch.sh && bash -n harvest/fetch.sh && echo "syntax ok"`
Expected: `syntax ok`. (Full run happens in Task 4 — it is long.)

- [ ] **Step 3: Commit**

```bash
git add harvest/fetch.sh
git commit -m "harvest: resumable rate-limited recipe downloader"
```

---

### Task 3: Refresh category index pages

**Files:**
- Create: `harvest/refresh_categories.sh`
- Modifies (data): `contribution/<category>.html`

- [ ] **Step 1: Write `harvest/refresh_categories.sh`**

```bash
#!/bin/bash
# Fetch the latest HTTP-200 snapshot of each category index page into contribution/.
# These pages define which recipes belong to which category.
set -u
cd "$(dirname "$0")/.."
DEST="contribution"
CATS="vegetables paneer soya daal curries rice roti dosas bread regional east \
snacks pakora chutney raita salad soup refreshment sweets cakes mushroom assorted \
microwave south chicken redmeat seafood egg nonvegsweets index"

for c in $CATS; do
  # newest 200 snapshot for this exact page
  ts=$(curl -s "http://web.archive.org/cdx/search/cdx?url=bawarchi.com/contribution/${c}.html&output=text&fl=timestamp&filter=statuscode:200&limit=-1" --max-time 60 2>/dev/null | tail -1)
  if [ -z "$ts" ]; then echo "no snapshot: $c"; continue; fi
  url="https://web.archive.org/web/${ts}id_/http://www.bawarchi.com/contribution/${c}.html"
  code=$(curl -sL "$url" -o "$DEST/${c}.html" -w "%{http_code}" --max-time 45 2>/dev/null || echo 000)
  sz=$(wc -c < "$DEST/${c}.html" 2>/dev/null || echo 0)
  echo "$c: $code ${sz}B (snapshot $ts)"
  [ "$code" = "200" ] && [ "$sz" -gt 200 ] || { echo "  FAILED, keeping old $c.html"; git checkout -- "$DEST/${c}.html" 2>/dev/null; }
  sleep 0.8
done
```

- [ ] **Step 2: Syntax check**

Run: `chmod +x harvest/refresh_categories.sh && bash -n harvest/refresh_categories.sh && echo "syntax ok"`
Expected: `syntax ok`.

- [ ] **Step 3: Commit**

```bash
git add harvest/refresh_categories.sh
git commit -m "harvest: refresh category index pages from latest snapshots"
```

> **Note:** `limit=-1` on the CDX API returns the most recent captures last; `tail -1` takes the newest. If a category returns nothing, the script keeps the existing 2001 file (`git checkout --`), so a pre-run commit of the current `contribution/` is not required but the fallback is safe either way.

---

### Task 4: Run the harvest and produce a report

**Files:**
- Create: `harvest/report.py`

- [ ] **Step 1: Record the baseline count**

Run: `ls contribution/ | grep -cE '^contrib[0-9]+\.html'`
Expected: `3735` (the starting point — note it).

- [ ] **Step 2: Refresh category pages, then fetch recipes**

Run:
```bash
bash harvest/refresh_categories.sh
bash harvest/fetch.sh 2>&1 | tee harvest/fetch.log
```
Expected: `fetch.sh` runs for a while (thousands of requests at ~0.8s each ⇒ tens of minutes). It is resumable — if interrupted, re-run the same command and it resumes. Final line: `DONE: total=… got=… skip=… fail=…`.

- [ ] **Step 3: Write `harvest/report.py`**

```python
#!/usr/bin/env python3
"""Report harvest completeness against the work-list."""
import re, pathlib
ROOT = pathlib.Path(__file__).parent.parent
worklist = (ROOT / "harvest" / "worklist.tsv").read_text().splitlines()[1:]
wanted = {ln.split("\t")[0] for ln in worklist if ln.strip()}
have = {p.name.lower() for p in (ROOT / "contribution").glob("contrib*.html")
        if p.stat().st_size > 200}
missing = sorted(wanted - have, key=lambda f: int(re.search(r"\d+", f).group()))
print(f"wanted (work-list): {len(wanted)}")
print(f"have on disk (>200B): {len(have)}")
print(f"still missing:       {len(missing)}")
if missing:
    print("missing sample:", missing[:20])
    (ROOT / "harvest" / "still-missing.txt").write_text("\n".join(missing) + "\n")
    print("full list -> harvest/still-missing.txt")
```

- [ ] **Step 4: Run the report**

Run: `uv run python harvest/report.py`
Expected: `have on disk` is close to `wanted` (~5,900). Some `still missing` is acceptable — those numbers were never archived with a usable capture. The list is written out, not hidden (spec: no silent caps).

- [ ] **Step 5: Commit the enlarged corpus + logs**

```bash
git add contribution harvest/report.py harvest/fetch-manifest.tsv harvest/fetch.log harvest/still-missing.txt
git commit -m "harvest: recover post-2001 recipes from Wayback ($(ls contribution | grep -cE '^contrib[0-9]+\.html') recipe pages)"
```

---

# Phase 2 — Parse to `recipes.json`

### Task 5: Category-membership map from index pages

**Files:**
- Create: `build_site.py` (first half — category map)

- [ ] **Step 1: Write the category-mapping section of `build_site.py`**

```python
#!/usr/bin/env python3
"""Parse contribution/*.html into site/recipes.json for the searchable site."""
import re, json, html, pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent
CONTRIB = ROOT / "contribution"
OUT = ROOT / "site" / "recipes.json"

# Primary category display order (slug -> nice name). 'south' is a tag, not primary.
CATEGORY_ORDER = [
    ("vegetables","Vegetables"),("paneer","Paneer"),("soya","Soya & Tofu"),
    ("daal","Daals"),("curries","Curries"),("rice","Rice & Pulaos"),
    ("roti","Rotis & Parathas"),("dosas","Dosas & Pancakes"),("bread","Breads & Pizzas"),
    ("regional","Regional Specialities"),("east","East / West / North"),("snacks","Snacks"),
    ("pakora","Pakoras, Vadas & Cutlets"),("chutney","Chutneys, Sauces & Pickles"),
    ("raita","Raitas"),("salad","Salads"),("soup","Soups & Stews"),
    ("refreshment","Refreshments"),("sweets","Sweets & Puddings"),("cakes","Cakes & Biscuits"),
    ("mushroom","Mushrooms"),("microwave","Microwave"),
    ("chicken","Chicken"),("redmeat","Red Meat"),("seafood","Seafood"),
    ("egg","Egg Dishes"),("nonvegsweets","Non-Veg Sweets"),("assorted","Assorted"),
]
CAT_NAME = dict(CATEGORY_ORDER)
CAT_PRIORITY = {slug: i for i, (slug, _) in enumerate(CATEGORY_ORDER)}
NONVEG_CATS = {"chicken","redmeat","seafood","egg","nonvegsweets"}
ALL_CAT_SLUGS = [s for s, _ in CATEGORY_ORDER] + ["south"]

def category_map():
    """recipe filename -> (primary_slug, is_south) using the index pages."""
    cats_for = defaultdict(set)
    for slug in ALL_CAT_SLUGS:
        page = CONTRIB / f"{slug}.html"
        if not page.exists():
            continue
        text = page.read_text(encoding="utf-8", errors="replace")
        for r in re.findall(r"contrib\d+\.html", text, re.IGNORECASE):
            cats_for[r.lower()].add(slug)
    primary = {}
    south = set()
    for r, cs in cats_for.items():
        if "south" in cs:
            south.add(r)
        known = [c for c in cs if c in CAT_PRIORITY]
        primary[r] = min(known, key=lambda c: CAT_PRIORITY[c]) if known else "assorted"
    return primary, south
```

- [ ] **Step 2: Smoke-test the map in isolation**

Run:
```bash
uv run python -c "import build_site as b; p,s=b.category_map(); print('mapped',len(p),'recipes;', len(s),'south'); import collections; print(collections.Counter(p.values()).most_common(6))"
```
Expected: several thousand recipes mapped; a Counter showing categories like `vegetables`, `snacks`, `sweets` with large counts. No traceback.

- [ ] **Step 3: Commit**

```bash
git add build_site.py
git commit -m "build_site: category-membership map from index pages"
```

---

### Task 6: Structured recipe extraction (TDD)

**Files:**
- Modify: `build_site.py` (add `extract_recipe`)
- Create: `tests/test_parser.py`

The recipe body sits in a `<blockquote>`: a heading line `<font color="880000" size="+1"><b>TITLE</b></font> … by <a>NAME</a>`, then ingredient lines separated by `<br>`, then `<b>Method</b>`, then method steps. Extraction splits on the Method marker.

- [ ] **Step 1: Write the failing test `tests/test_parser.py`**

```python
import pathlib, build_site as b

CONTRIB = pathlib.Path(__file__).parent.parent / "contribution"

def test_grilled_apple_toast():
    r = b.extract_recipe(CONTRIB / "contrib1.html")
    assert r is not None
    assert r["title"] == "Grilled Apple Toast"
    assert r["contributor"] == "Bhavana Jain"
    # ingredients include the bread slices line, method excludes it
    assert any("Bread Slices" in x for x in r["ingredients"])
    assert not any("Bread Slices" in x for x in r["method"])
    # method has the numbered toaster step
    assert any("toaster" in x.lower() for x in r["method"])
    # method marker itself is not a step
    assert not any(x.strip().lower() == "method" for x in r["method"])

def test_degrades_gracefully_on_missing():
    r = b.extract_recipe(CONTRIB / "does-not-exist.html")
    assert r is None
```

- [ ] **Step 2: Run it, expect failure**

Run: `cd ~/Documents/projects/bawarchi && uv run --with pytest pytest tests/test_parser.py -v`
Expected: FAIL — `AttributeError`/`module 'build_site' has no attribute 'extract_recipe'`.

- [ ] **Step 3: Add `extract_recipe` to `build_site.py`**

```python
BLOCKQUOTE_RE = re.compile(r"<blockquote>(.*?)</blockquote>", re.DOTALL | re.IGNORECASE)
HEADING_RE = re.compile(
    r'<font[^>]*size="\+1"[^>]*>\s*<b>(.*?)</b>\s*</font>(.*?)(?:<p|<br)',
    re.DOTALL | re.IGNORECASE)
TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.IGNORECASE)
METHOD_MARKER_RE = re.compile(r"<b>\s*Method\s*</b>", re.IGNORECASE)

def _clean(fragment):
    """HTML fragment -> list of non-empty text lines, split on <br>/<p>."""
    fragment = re.sub(r"<a [^>]*(?:khojnet|samachar|indiaplaza|ads\.)[^>]*>.*?</a>",
                      "", fragment, flags=re.DOTALL | re.IGNORECASE)
    fragment = re.sub(r"<img [^>]*>", "", fragment, flags=re.IGNORECASE)
    parts = re.split(r"<br\s*/?>|<p\s*/?>|</p>", fragment, flags=re.IGNORECASE)
    lines = []
    for p in parts:
        t = html.unescape(re.sub(r"<[^>]+>", " ", p))
        t = re.sub(r"[ \t\xa0]+", " ", t).strip()
        if t:
            lines.append(t)
    return lines

def _title_from_tag(s):
    m = TITLE_TAG_RE.search(s)
    if not m:
        return "Untitled"
    t = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    t = re.sub(r"^Bawarchi\s*:\s*Contributions\s*:\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"<!--.*?-->", "", t).strip()
    return t or "Untitled"

def extract_recipe(path):
    try:
        s = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    bq = BLOCKQUOTE_RE.search(s)
    block = bq.group(1) if bq else s

    # Title + contributor from the heading line
    hm = HEADING_RE.search(block)
    if hm:
        raw_title = html.unescape(re.sub(r"<[^>]+>", " ", hm.group(1)))
        title = re.sub(r"\s+", " ", raw_title).strip() or _title_from_tag(s)
        after = hm.group(2)
        cm = re.search(r"\bby\b(.*)", after, re.IGNORECASE | re.DOTALL)
        contributor = None
        if cm:
            c = html.unescape(re.sub(r"<[^>]+>", " ", cm.group(1)))
            contributor = re.sub(r"\s+", " ", c).strip() or None
    else:
        title = _title_from_tag(s)
        contributor = None

    # Body after the heading, split on the Method marker
    body = block[hm.end():] if hm else block
    parts = METHOD_MARKER_RE.split(body, maxsplit=1)
    ingredients = _clean(parts[0])
    method = _clean(parts[1]) if len(parts) > 1 else []

    # Drop a leading echoed title / stray "by ..." line from ingredients
    ingredients = [x for x in ingredients
                   if x.lower() != title.lower() and not re.match(r"(?i)^by\b", x)]
    return {"title": title, "contributor": contributor,
            "ingredients": ingredients, "method": method}
```

- [ ] **Step 4: Run the test, expect pass**

Run: `uv run --with pytest pytest tests/test_parser.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Spot-check a later-era recipe**

Run:
```bash
uv run python -c "import build_site as b, pathlib, json; \
p=sorted(pathlib.Path('contribution').glob('contrib5*.html'))[:1]; \
print(json.dumps(b.extract_recipe(p[0]), indent=2, ensure_ascii=False)[:800]) if p else print('none in 5xxx range yet')"
```
Expected: a plausible title, contributor, ingredients and method — confirming the parser survives markup drift. If a field is empty it should be `null`/`[]`, never a crash.

- [ ] **Step 6: Commit**

```bash
git add build_site.py tests/test_parser.py
git commit -m "build_site: structured recipe extraction with parser test"
```

---

### Task 7: Assemble `recipes.json` and build stats

**Files:**
- Modify: `build_site.py` (add `main`)

- [ ] **Step 1: Add `main()` to `build_site.py`**

```python
def is_veg(primary, ingredients, method):
    if primary in NONVEG_CATS:
        return False
    blob = " ".join(ingredients + method).lower()
    meat = ("chicken","mutton","lamb","beef","pork","fish","prawn","shrimp",
            "crab","egg ","eggs","bacon","ham ","meat")
    return not any(w in blob for w in meat)

def main():
    primary, south = category_map()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    recipes = []
    files = sorted(CONTRIB.glob("contrib*.html"),
                   key=lambda p: int(re.search(r"\d+", p.name).group()))
    dropped = 0
    for path in files:
        if path.stat().st_size <= 200:
            dropped += 1; continue
        rec = extract_recipe(path)
        if rec is None or not rec["title"] or rec["title"] == "Untitled":
            dropped += 1; continue
        fname = path.name.lower()
        prim = primary.get(fname, "assorted")
        veg = is_veg(prim, rec["ingredients"], rec["method"])
        recipes.append({
            "id": int(re.search(r"\d+", fname).group()),
            "title": rec["title"],
            "contributor": rec["contributor"],
            "category": prim,
            "categoryName": CAT_NAME.get(prim, "Assorted"),
            "south": fname in south,
            "isVeg": veg,
            "ingredients": rec["ingredients"],
            "method": rec["method"],
        })
    OUT.write_text(json.dumps(recipes, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    by_cat = Counter(r["category"] for r in recipes)
    veg_n = sum(1 for r in recipes if r["isVeg"])
    print(f"recipes written: {len(recipes)}  (dropped {dropped})")
    print(f"vegetarian: {veg_n}   non-veg: {len(recipes)-veg_n}")
    print(f"no ingredients: {sum(1 for r in recipes if not r['ingredients'])}"
          f"   no method: {sum(1 for r in recipes if not r['method'])}")
    print("by category:", dict(sorted(by_cat.items(), key=lambda kv: -kv[1])))
    print(f"-> {OUT}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Build the JSON**

Run: `cd ~/Documents/projects/bawarchi && uv run python build_site.py`
Expected: "recipes written: ~5,700+ (dropped …)"; a sensible veg/non-veg split; per-category counts; `site/recipes.json` created. `no ingredients` / `no method` should be a small minority.

- [ ] **Step 3: Validate the JSON**

Run: `uv run python -c "import json; d=json.load(open('site/recipes.json')); print(len(d),'recipes'); print(d[0]['title'], '/', d[0]['category'], '/ veg=', d[0]['isVeg'])"`
Expected: count matches the build log; first record looks correct.

- [ ] **Step 4: Commit**

```bash
git add build_site.py site/recipes.json
git commit -m "build_site: assemble recipes.json with categories, veg flag, stats"
```

---

# Phase 3 — Single-Page Site

### Task 8: Build the app (`index.html`, `styles.css`, `app.js`)

**Files:**
- Create: `site/index.html`, `site/styles.css`, `site/app.js`

Design intent: warm family-cookbook feel — cream/paper background, serif recipe titles, generous whitespace, contributor names surfaced. Search box on top, category chips + veg-only toggle below, results list, and a recipe view reachable at `#/recipe/<id>`.

- [ ] **Step 1: Write `site/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Bawarchi Recipe Collection</title>
<link rel="stylesheet" href="styles.css">
</head>
<body>
<header>
  <h1>The Bawarchi Recipe Collection</h1>
  <p class="tagline">Home recipes sent in by readers of <em>bawarchi.com</em>, c. 2001,
     recovered from the Internet Archive.</p>
  <input id="q" type="search" placeholder="Search recipes, ingredients, cooks…" autofocus>
  <div id="filters">
    <label class="veg-toggle"><input type="checkbox" id="vegOnly"> Vegetarian only</label>
    <div id="chips"></div>
  </div>
  <p id="count"></p>
</header>
<main>
  <ul id="results"></ul>
  <article id="recipe" hidden></article>
</main>
<footer>Recovered from the Wayback Machine. Recipes are readers' own, untested.</footer>
<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `site/styles.css`**

```css
:root{--paper:#faf6ef;--ink:#2b2622;--accent:#8a2b1e;--muted:#8c8378;--line:#e4dccd;}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:Georgia,"Iowan Old Style","Times New Roman",serif;line-height:1.5}
header{max-width:820px;margin:0 auto;padding:2.4rem 1.2rem 1rem;text-align:center}
h1{font-size:2.4rem;margin:0 0 .2rem;letter-spacing:.5px}
.tagline{color:var(--muted);font-style:italic;margin:.2rem 0 1.4rem}
#q{width:100%;max-width:640px;padding:.7rem 1rem;font-size:1.05rem;font-family:inherit;
  border:1px solid var(--line);border-radius:8px;background:#fff}
#filters{margin:1rem 0 .3rem}
.veg-toggle{display:inline-block;margin-bottom:.6rem;color:var(--ink);font-size:.9rem;cursor:pointer}
#chips{display:flex;flex-wrap:wrap;gap:.4rem;justify-content:center}
.chip{padding:.25rem .7rem;border:1px solid var(--line);border-radius:999px;background:#fff;
  cursor:pointer;font-size:.82rem;color:var(--ink)}
.chip.active{background:var(--accent);color:#fff;border-color:var(--accent)}
#count{color:var(--muted);font-size:.85rem;margin:.6rem 0}
main{max-width:820px;margin:0 auto;padding:0 1.2rem 3rem}
#results{list-style:none;padding:0;margin:0}
#results li{padding:.8rem .4rem;border-bottom:1px solid var(--line);cursor:pointer}
#results li:hover{background:#fff}
#results .rtitle{font-size:1.15rem;color:var(--accent)}
#results .rmeta{color:var(--muted);font-size:.82rem}
#recipe{background:#fff;border:1px solid var(--line);border-radius:10px;padding:1.6rem 1.8rem}
#recipe h2{color:var(--accent);margin:.2rem 0 .1rem;font-size:1.8rem}
#recipe .by{color:var(--muted);font-style:italic;margin-bottom:1.2rem}
#recipe h3{font-size:1rem;letter-spacing:.5px;text-transform:uppercase;color:var(--muted);
  border-bottom:1px solid var(--line);padding-bottom:.2rem;margin-top:1.4rem}
#recipe ul,#recipe ol{padding-left:1.3rem}
#recipe li{margin:.3rem 0}
.back{display:inline-block;margin-bottom:1rem;color:var(--accent);cursor:pointer;
  text-decoration:underline;background:none;border:none;font:inherit;padding:0}
.badge{font-size:.7rem;padding:.1rem .5rem;border-radius:4px;margin-left:.5rem;vertical-align:middle}
.badge.veg{background:#e5f0e0;color:#2f6b2f}.badge.nonveg{background:#f5e2df;color:#8a2b1e}
footer{text-align:center;color:var(--muted);font-size:.78rem;padding:2rem 1rem 3rem}
```

- [ ] **Step 3: Write `site/app.js`**

```javascript
let RECIPES = [];
let activeCat = null;      // slug or null = all
let vegOnly = false;

const els = {
  q: document.getElementById('q'),
  chips: document.getElementById('chips'),
  vegOnly: document.getElementById('vegOnly'),
  count: document.getElementById('count'),
  results: document.getElementById('results'),
  recipe: document.getElementById('recipe'),
};

fetch('recipes.json').then(r => r.json()).then(data => {
  RECIPES = data;
  buildChips();
  route();
});

function buildChips() {
  const order = [];
  for (const r of RECIPES) if (!order.find(o => o.slug === r.category))
    order.push({ slug: r.category, name: r.categoryName });
  els.chips.innerHTML = '';
  const all = chip('All', null); els.chips.appendChild(all);
  order.forEach(o => els.chips.appendChild(chip(o.name, o.slug)));
}
function chip(label, slug) {
  const b = document.createElement('button');
  b.className = 'chip' + ((slug === activeCat) ? ' active' : '');
  b.textContent = label;
  b.onclick = () => { activeCat = slug; buildChips(); render(); };
  return b;
}

function norm(s){ return (s||'').toLowerCase(); }
function matches(r, terms) {
  if (!terms.length) return true;
  const hay = norm(r.title) + ' ' + norm(r.contributor) + ' ' + norm(r.ingredients.join(' '));
  return terms.every(t => hay.includes(t));
}

function render() {
  els.recipe.hidden = true;
  els.results.hidden = false;
  const terms = els.q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const list = RECIPES.filter(r =>
    (!activeCat || r.category === activeCat) &&
    (!vegOnly || r.isVeg) &&
    matches(r, terms));
  els.count.textContent = `${list.length} recipe${list.length === 1 ? '' : 's'}`;
  els.results.innerHTML = '';
  const frag = document.createDocumentFragment();
  list.slice(0, 400).forEach(r => {
    const li = document.createElement('li');
    li.innerHTML = `<div class="rtitle">${esc(r.title)}</div>` +
      `<div class="rmeta">${r.contributor ? 'by ' + esc(r.contributor) + ' · ' : ''}` +
      `${esc(r.categoryName)}</div>`;
    li.onclick = () => { location.hash = '#/recipe/' + r.id; };
    frag.appendChild(li);
  });
  els.results.appendChild(frag);
  if (list.length > 400) {
    const li = document.createElement('li');
    li.className = 'rmeta';
    li.textContent = `Showing first 400 of ${list.length}. Refine your search to see more.`;
    els.results.appendChild(li);
  }
}

function showRecipe(id) {
  const r = RECIPES.find(x => x.id === id);
  if (!r) { location.hash = ''; return; }
  els.results.hidden = true;
  els.recipe.hidden = false;
  const badge = r.isVeg ? '<span class="badge veg">veg</span>'
                        : '<span class="badge nonveg">non-veg</span>';
  els.recipe.innerHTML =
    `<button class="back">&larr; Back</button>` +
    `<h2>${esc(r.title)}${badge}</h2>` +
    `<div class="by">${r.contributor ? 'by ' + esc(r.contributor) : ''} · ${esc(r.categoryName)}</div>` +
    (r.ingredients.length ? `<h3>Ingredients</h3><ul>${r.ingredients.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : '') +
    (r.method.length ? `<h3>Method</h3><ol>${r.method.map(m => `<li>${esc(m.replace(/^\d+[.)]\s*/, ''))}</li>`).join('')}</ol>` : '');
  els.recipe.querySelector('.back').onclick = () => history.back();
  window.scrollTo(0, 0);
}

function route() {
  const m = location.hash.match(/#\/recipe\/(\d+)/);
  if (m) showRecipe(parseInt(m[1], 10));
  else render();
}

function esc(s){ return (s||'').replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

els.q.addEventListener('input', () => { if (!location.hash) render(); else location.hash=''; });
els.vegOnly.addEventListener('change', () => { vegOnly = els.vegOnly.checked; render(); });
window.addEventListener('hashchange', route);
```

- [ ] **Step 4: Commit**

```bash
git add site/index.html site/styles.css site/app.js
git commit -m "site: single-page searchable app (search, categories, veg toggle, recipe view)"
```

---

### Task 9: Local verification

- [ ] **Step 1: Serve locally**

Run: `cd ~/Documents/projects/bawarchi/site && uv run python -m http.server 8765`
Then open `http://localhost:8765/` in a browser (leave the server running in a background shell).

- [ ] **Step 2: Manual checks (confirm each)**

  - [ ] Page loads; recipe count shows the full total.
  - [ ] Typing `paneer` filters the list; results mention paneer.
  - [ ] Typing `chicken tikka` returns chicken recipes; ticking **Vegetarian only** removes them and the count drops.
  - [ ] Clicking a category chip filters to that category; "All" restores.
  - [ ] Clicking a recipe opens the recipe view with ingredients + numbered method; the URL gains `#/recipe/<id>`.
  - [ ] Reloading that `#/recipe/<id>` URL opens the same recipe directly (deep link).
  - [ ] **Back** returns to the list with the previous search/filter intact.
  - [ ] Narrow the browser to phone width: layout stays legible, search usable.

- [ ] **Step 3: Stop the server** (Ctrl-C) once checks pass.

> No commit — verification only. If a check fails, fix the relevant file from Task 8 and re-verify before proceeding.

---

# Phase 4 — Deploy to GitHub Pages

### Task 10: Publish

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write a short `README.md`**

```markdown
# The Bawarchi Recipe Collection

A searchable web front-end for the readers'-contributions recipe archive of
bawarchi.com (c. 2001), recovered from the Internet Archive.

- `harvest/` — scripts that rebuild the recipe corpus from the Wayback Machine.
- `build_site.py` — parses `contribution/*.html` into `site/recipes.json`.
- `site/` — the static single-page app (deployed via GitHub Pages).

Rebuild: `uv run python harvest/enumerate.py && bash harvest/fetch.sh && uv run python build_site.py`
```

- [ ] **Step 2: Confirm GitHub account + choose repo owner**

Run: `gh auth status && gh api user -q .login`
Expected: authenticated; note the login. Ask the user whether to create under a personal repo or the `jaymoore-research` org, and whether public is acceptable (it is a recovered public archive) before creating.

- [ ] **Step 3: Create the repo and push**

```bash
cd ~/Documents/projects/bawarchi
git add README.md
git commit -m "docs: project README"
gh repo create bawarchi-recipes --public --source=. --remote=origin --push
```
(Adjust owner/visibility per Step 2's answer, e.g. `jaymoore-research/bawarchi-recipes`.)

- [ ] **Step 4: Enable Pages serving from `/site`**

GitHub Pages needs the app at a served path. Serve from the `main` branch `/docs` folder by relocating the app, or publish the `site/` folder via a Pages workflow. Simplest: rename `site/` → `docs/` and set Pages source to `main` `/docs`.

```bash
git mv site docs
# fix the build output path in build_site.py: OUT = ROOT / "docs" / "recipes.json"
sed -i '' 's#"site" / "recipes.json"#"docs" / "recipes.json"#' build_site.py
uv run python build_site.py           # regenerate docs/recipes.json in new location
git add -A && git commit -m "deploy: serve app from docs/ for GitHub Pages"
git push
gh api -X POST repos/:owner/bawarchi-recipes/pages -f "source[branch]=main" -f "source[path]=/docs" 2>/dev/null || \
  echo "Enable Pages in repo Settings → Pages: branch main, folder /docs"
```

- [ ] **Step 5: Verify the live site**

Run: `gh api repos/:owner/bawarchi-recipes/pages -q .html_url`
Open the URL (allow a minute for first build). Confirm search works and a deep link loads. Share this URL.

- [ ] **Step 6: Final commit**

```bash
git add -A && git commit -m "deploy: Bawarchi recipe collection live on GitHub Pages" --allow-empty
git push
```

---

## Self-Review notes

- **Spec coverage:** Phase 1 (enumerate/fetch/refresh/report) = spec §Phase 1a–1c + acceptance (no silent caps via `report.py`/`still-missing.txt`). Phase 2 Tasks 5–7 = spec §2a (`recipes.json`, all fields, graceful degradation, stats). Phase 3 Tasks 8–9 = spec §2b (search, chips, veg toggle, contributor, deep links, family feel) + acceptance. Phase 4 Task 10 = spec §2c (GitHub Pages). ✅
- **Non-goals honoured:** no backend, no per-recipe files, no images, existing PDF untouched.
- **Type consistency:** `extract_recipe` returns `{title, contributor, ingredients, method}`; `main()` consumes exactly those plus category-map output; `recipes.json` fields (`id,title,contributor,category,categoryName,south,isVeg,ingredients,method`) match `app.js` usage (`r.title,r.contributor,r.category,r.categoryName,r.isVeg,r.ingredients,r.method,r.id`). ✅
- **Known soft spots:** parser tuned on 2001 markup — Task 6 Step 5 spot-checks a later-era page; if later pages differ structurally, widen `HEADING_RE`/`METHOD_MARKER_RE` before Task 7. `is_veg` keyword check is conservative and may mislabel edge cases (e.g. "egg-free"); acceptable for a toggle, not a hard filter.
```
