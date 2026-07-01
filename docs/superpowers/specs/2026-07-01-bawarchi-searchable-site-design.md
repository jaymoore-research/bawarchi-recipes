# Bawarchi searchable recipe site — design

**Date:** 2026-07-01
**Project dir:** `~/Documents/projects/bawarchi`
**Goal:** A hosted, searchable, shareable single-page website of the full Bawarchi
readers'-contributions recipe archive, grown as complete as possible from the
Internet Archive before launch.

## Context

`bawarchi.com` (c. 2001) ran a "Readers' Contributions" section: home cooks
sending in their own recipes. The site is long dead; only the Wayback Machine
holds it. A prior effort mirrored a single 2001-02-01 snapshot into
`contribution/` — **3,735 recipe pages** (`contribNNN.html`) plus ~30 category
index pages — and compiled them into a vegetarian-only PDF via `build-book.py`.

This project supersedes the PDF: a searchable web front-end covering the
**whole archive (vegetarian and non-vegetarian)**, hosted at a shareable link.

### Assets already on disk
- `contribution/contribNNN.html` — 3,735 individual recipe pages (title,
  `by <contributor>`, ingredients, method).
- `contribution/<category>.html` — ~30 category index pages listing recipes by
  title + contributor (vegetables, curries, sweets, chicken, seafood, …).
- `build-book.py` — existing parser: category ordering, veg sub-category
  bucketing by ingredient keywords, non-veg detection. Reusable logic.
- `manifest.tsv`, `scrape.sh` — record of the original resumable Wayback pull.

### Wayback reconnaissance (verified via CDX API, 2026-07-01)
- **5,920 distinct `contribNNN.html`** pages archived across all snapshots
  (highest number: `contrib6032`) → **~2,185 net-new recipes** beyond the local
  3,735.
- URL scheme unchanged over the site's life: `…/contribution/contribNNN.html`.
- Category index pages have 40–100 snapshots each; a later **`microwave`**
  category exists that the 2001 set lacks.

## Scope decisions (confirmed with user)
- **Recipes:** everything — veg and non-veg. Non-veg kept and flagged, with a
  veg-only toggle in the UI.
- **Sharing:** hosted link (GitHub Pages).
- **Rendering:** single-page app — one `index.html` + `recipes.json`, client-side
  search, deep links. No per-recipe files, no backend.
- **Ordering:** Wayback harvest first, so the first launch is as complete as
  possible; then build + deploy.

## Non-goals (YAGNI)
- No server, database, or dynamic backend.
- No per-recipe SEO/static pages (family sharing, not public SEO).
- No editing/CMS/user accounts.
- No image recovery (recipes are text; archived pages carry ads/banners only).
- Not touching the existing PDF or booklet artefacts.

---

## Phase 1 — Wayback harvest

Grow `contribution/` from ~3,735 to the full ~5,920 recipes, plus refreshed
category indexes.

### 1a. Enumerate the master recipe list
Query the CDX API for every distinct `contribNNN.html` under
`bawarchi.com/contribution*`, collapsed on `original`. For each URL keep the
**best snapshot**: the most recent capture with `statuscode:200`. Output a
work-list TSV: `filename  wayback_timestamp  original_url`.

### 1b. Fetch missing recipes
For each recipe not already present locally (>200 bytes), download from
`https://web.archive.org/web/<timestamp>id_/<original_url>`. The `id_` suffix
returns the **raw archived HTML** without the Wayback toolbar/rewrites.

Requirements:
- **Resumable:** skip files already present and >200 bytes (mirror `scrape.sh`).
- **Rate-limited:** ~0.8s between requests, up to 3 retries with backoff.
- **Manifest:** append `file  http  size  attempts` per attempt; delete
  truncated/failed downloads so re-runs retry them.
- On repeated failure for a snapshot, fall back to the next-most-recent 200
  capture before giving up.

### 1c. Refresh category indexes
Download the latest 200 snapshot of each category index page (all names seen in
CDX, **including `microwave`**) into `contribution/`, overwriting the 2001
versions. These are the authoritative source of category membership and titles
for the enlarged recipe set.

### Phase 1 acceptance
- `contribution/` holds close to 5,920 `contribNNN.html` (some numbers are gaps
  / were never archived — that is expected; log the shortfall, don't fail).
- A harvest report prints: recipes before, recipes after, net-new, and count
  still missing after retries.
- **No silent caps:** any recipe on the master list not obtained is listed
  explicitly in the report.

---

## Phase 2 — Parse + build the site

### 2a. Parser → `recipes.json`
Extend `build-book.py`'s extraction. For each `contribNNN.html`:
- `id` — the recipe number (from filename).
- `title` — cleaned dish name.
- `contributor` — text after `by …` (nullable).
- `category` — from which category index page lists the recipe; fall back to
  `build-book.py`'s ingredient-keyword inference for orphans.
- `subcategory` — veg sub-bucket where applicable (existing logic).
- `ingredients[]`, `method[]` — parsed line lists.
- `isVeg` — boolean; non-veg categories (chicken, seafood, redmeat, egg,
  nonvegsweets) and non-veg keyword hits flag `false`.

Emit a single `recipes.json`. Also emit lightweight build stats (counts per
category, veg/non-veg split, recipes with no method/ingredients).

**Parser robustness:** archived pages vary in markup across years. The parser
must degrade gracefully — a recipe missing ingredients or contributor is still
included, with the missing field null/empty, never dropped.

### 2b. Single-page site (`index.html` + `app.js` + `styles.css` + `recipes.json`)
- **Search:** client-side full-text over title + ingredients + contributor.
  Instant filter as you type. Small, self-contained matcher (no heavy deps; a
  minimal tokenised index is fine for ~6k recipes).
- **Browse:** category chips (display order from `build-book.py`); a **veg-only
  toggle**; result count shown.
- **Recipe view:** title, `by <contributor>`, ingredients list, numbered method.
  Deep-linkable via `#/recipe/<id>`; back returns to the search/browse state.
- **Intro:** a short note explaining what bawarchi.com was (readers'
  contributions, c. 2001, recovered from the Internet Archive).
- **Feel — "family cookbook":** warm cream/paper palette, a serif for recipe
  titles, generous whitespace, contributor names surfaced prominently. Legible
  on phone and laptop. Distinctive and intentional, not a default template.

### 2c. Deploy
- Git-init the project, push to a GitHub repo, enable **GitHub Pages**.
- The site is static: `index.html` + assets + `recipes.json` at the repo root
  (or `/docs`). Re-deploying after a future harvest is just a rebuild + push.

### Phase 2 acceptance
- `recipes.json` contains every harvested recipe with the fields above.
- Opening `index.html` locally: search returns sensible matches; category chips
  and veg-only toggle filter correctly; a recipe opens and deep-links.
- Live GitHub Pages URL loads and works on a phone.
- Build stats reported; anything dropped or uncategorised is logged, not hidden.

---

## Risks / open points
- **Yield uncertainty:** not all 5,920 numbers were necessarily archived with a
  usable 200 capture; final count may be < 5,920. Reported honestly, not padded.
- **Markup drift:** later-year pages may parse imperfectly. Parser degrades
  gracefully; a spot-check of new recipes validates extraction.
- **Duplicate titles:** the same dish appears under multiple numbers/contributors.
  Kept as distinct recipes (they are distinct submissions); not de-duplicated.
- **Wayback rate limits / flakiness:** mitigated by resumable manifest + backoff.

## Rough sequence
1. Phase 1a–1c: harvest (long-running, resumable, mostly unattended).
2. Phase 2a: parser + `recipes.json` + stats.
3. Phase 2b: single-page site.
4. Phase 2c: GitHub repo + Pages deploy.
