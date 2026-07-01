# The Bawarchi Recipe Collection

A searchable web front-end for the readers'-contributions recipe archive of
[bawarchi.com](https://web.archive.org/web/2004/http://www.bawarchi.com/contribution/)
(c. 2001–2008), recovered from the Internet Archive.

## Layout

- `harvest/` — scripts that rebuild the recipe corpus from the Wayback Machine.
  - `enumerate.py` — list every archived recipe page → `worklist.tsv`.
  - `fetch_parallel.sh` — download the still-missing recipes (parallel, resumable).
  - `fetch_one.sh` — per-recipe worker: validate completeness, fall back to a
    ~2004 snapshot when the newest capture is a truncated stub.
  - `refresh_categories.sh` — refresh the category index pages.
  - `report.py` — completeness report (disk vs work-list).
- `contribution/` — the recovered recipe pages + category index pages.
- `build_site.py` — parses `contribution/*.html` → `site/recipes.json`.
- `site/` — the static single-page app (deployed via GitHub Pages).

## Rebuild / top up the collection

The harvest is fully resumable — re-run it any time to add recipes the Wayback
Machine has since captured, then rebuild the site:

```bash
uv run python harvest/enumerate.py        # refresh the master list (optional)
JOBS=8 bash harvest/fetch_parallel.sh     # download missing recipes (repeatable)
uv run python harvest/report.py           # completeness report
uv run python build_site.py               # regenerate site/recipes.json
```

Some late-added recipes were only ever archived as truncated pages and cannot be
fully recovered; `harvest/report.py` lists what is still missing.

## Run locally

```bash
cd site && python3 -m http.server 8765    # then open http://localhost:8765
```
