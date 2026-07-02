#!/usr/bin/env python3
"""Parse contribution/*.html into site/recipes.json for the searchable site.

The archive spans two markup eras and the extractor handles both:
  - 2001 era: lowercase tags, `<font color=... size="+1"><b>TITLE</b></font> by NAME`,
    `<br>`-separated ingredients, `<b>Method</b>`, numbered method lines.
  - 2007-2008 (sify) era: UPPERCASE tags, `size=+1` unquoted, `<B>Method:</B>`,
    `<OL><LI>` method steps, plus U+FFFD replacement-char noise and sify nav cruft.
Both eras wrap the recipe in a `<blockquote>`, which we use to isolate content.
"""
import re
import json
import html
import pathlib
from collections import defaultdict, Counter

ROOT = pathlib.Path(__file__).parent
CONTRIB = ROOT / "contribution"
OUT = ROOT / "site" / "recipes.json"

CATEGORY_ORDER = [
    ("vegetables", "Vegetables"), ("paneer", "Paneer"), ("soya", "Soya & Tofu"),
    ("daal", "Daals"), ("curries", "Curries"), ("rice", "Rice & Pulaos"),
    ("roti", "Rotis & Parathas"), ("dosas", "Dosas & Pancakes"), ("bread", "Breads & Pizzas"),
    ("regional", "Regional Specialities"), ("east", "East / West / North"), ("snacks", "Snacks"),
    ("pakora", "Pakoras, Vadas & Cutlets"), ("chutney", "Chutneys, Sauces & Pickles"),
    ("raita", "Raitas"), ("salad", "Salads"), ("soup", "Soups & Stews"),
    ("refreshment", "Refreshments"), ("sweets", "Sweets & Puddings"), ("cakes", "Cakes & Biscuits"),
    ("mushroom", "Mushrooms"), ("microwave", "Microwave"),
    ("chicken", "Chicken"), ("redmeat", "Red Meat"), ("seafood", "Seafood"),
    ("egg", "Egg Dishes"), ("nonvegsweets", "Non-Veg Sweets"), ("assorted", "Assorted"),
]
CAT_NAME = dict(CATEGORY_ORDER)
CAT_PRIORITY = {slug: i for i, (slug, _) in enumerate(CATEGORY_ORDER)}
NONVEG_CATS = {"chicken", "redmeat", "seafood", "egg", "nonvegsweets"}
ALL_CAT_SLUGS = [s for s, _ in CATEGORY_ORDER] + ["south"]


def category_map():
    """recipe filename -> primary category slug, plus the set of 'south' recipes."""
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


# --- recipe extraction ---------------------------------------------------

BLOCKQUOTE_RE = re.compile(r"<blockquote>(.*?)</blockquote>", re.DOTALL | re.IGNORECASE)
# size="+1" (2001, quoted) OR size=+1 (2008, unquoted); tags may be upper/lower case.
HEADING_RE = re.compile(
    r'<font[^>]*size="?\+1"?[^>]*>\s*<b>(.*?)</b>\s*</font>(.*?)(?:<p|<br)',
    re.DOTALL | re.IGNORECASE)
TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.IGNORECASE)
# <b>Method</b> and <B>Method:</B> and <b>Method :</b>
METHOD_MARKER_RE = re.compile(r"<b>\s*method\s*:?\s*</b>", re.IGNORECASE)
LABEL_ONLY_RE = re.compile(r"^(method|ingredients|preparation)\s*:?\s*$", re.IGNORECASE)


def _clean(fragment):
    """HTML fragment -> list of non-empty text lines, split on <br>/<p>/<li>."""
    # drop ads, sify widgets, scripts, images before splitting
    fragment = re.sub(r"<a [^>]*(?:khojnet|samachar|indiaplaza|sify|ads\.|doubleclick)[^>]*>.*?</a>",
                      "", fragment, flags=re.DOTALL | re.IGNORECASE)
    fragment = re.sub(r"<script.*?</script>", "", fragment, flags=re.DOTALL | re.IGNORECASE)
    fragment = re.sub(r"<style.*?</style>", "", fragment, flags=re.DOTALL | re.IGNORECASE)
    fragment = re.sub(r"<img [^>]*>", "", fragment, flags=re.IGNORECASE)
    parts = re.split(r"<br\s*/?>|<p\s*/?>|</p>|<li\s*/?>|</li>", fragment, flags=re.IGNORECASE)
    lines = []
    for p in parts:
        t = html.unescape(re.sub(r"<[^>]+>", " ", p))
        t = t.replace("�", " ")                       # U+FFFD noise from bad encoding
        t = re.sub(r"\s+", " ", t).strip()            # collapse newlines/tabs too
        t = t.lstrip(">").strip()                     # stray '>' left by heading regex
        if not t or LABEL_ONLY_RE.match(t):
            continue
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
    except (OSError, FileNotFoundError):
        return None

    # Both eras wrap the recipe in a blockquote; sify pages may have several
    # (nav/ads), so take the largest — that's the recipe body.
    blocks = BLOCKQUOTE_RE.findall(s)
    block = max(blocks, key=len) if blocks else s

    # Title: the <title> tag is clean title-case in both eras; the in-body
    # heading is often ALL CAPS, so prefer the tag.
    title = _title_from_tag(s)

    # Contributor: the "by NAME" text that follows the heading (2001 era);
    # frequently absent in the sify era -> null.
    hm = HEADING_RE.search(block)
    contributor = None
    if hm:
        cm = re.search(r"\bby\b(.*)", hm.group(2), re.IGNORECASE | re.DOTALL)
        if cm:
            c = html.unescape(re.sub(r"<[^>]+>", " ", cm.group(1)))
            c = re.sub(r"\s+", " ", c).replace("�", "").strip()
            contributor = c or None

    # Body after the heading, split on the Method marker.
    body = block[hm.end():] if hm else block
    parts = METHOD_MARKER_RE.split(body, maxsplit=1)
    ingredients = _clean(parts[0])
    method = _clean(parts[1]) if len(parts) > 1 else []

    # Drop a leading echoed title / stray "by ..." / "Email:" lines from ingredients.
    ingredients = [x for x in ingredients
                   if x.lower() != title.lower()
                   and not re.match(r"(?i)^by\b", x)
                   and not re.match(r"(?i)^e-?mail\b", x)]
    return {"title": title, "contributor": contributor,
            "ingredients": ingredients, "method": method}


# --- assembly ------------------------------------------------------------

# Title-keyword inference for recipes not listed in any category index page
# (mostly post-2001 additions). Checked in priority order; distinctive/non-veg
# cues first so e.g. "Chicken Biryani" lands in chicken, not rice.
INFER_RULES = [
    ("chicken",   ["chicken", "murgh", "tandoori chicken"]),
    ("seafood",   ["fish", "prawn", "shrimp", "crab", "lobster", "squid", "meen"]),
    ("redmeat",   ["mutton", "lamb", "beef", "pork", "keema", "kheema", "goat"]),
    ("egg",       ["egg", "omelet", "omelette", "anda"]),
    ("paneer",    ["paneer"]),
    ("soya",      ["tofu", "soya", "soy "]),
    ("mushroom",  ["mushroom"]),
    ("dosas",     ["dosa", "uttapam", "uthappam", "appam", "pesarattu", "adai", "paniyaram"]),
    ("pakora",    ["pakora", "pakoda", "bajji", "bonda", "vada", "vadai", "cutlet", "bhaji"]),
    ("rice",      ["biryani", "biriyani", "pulao", "pulav", "pongal", "fried rice",
                   "bhath", "bath", "rice", "khichdi", "kichadi"]),
    ("roti",      ["roti", "paratha", "parantha", "naan", "chapati", "chapathi",
                   "thepla", "poori", "puri", "kulcha", "phulka"]),
    ("bread",     ["pizza", "sandwich", "toast", "burger", "bread"]),
    ("chutney",   ["chutney", "pickle", "thokku", "podi", "achar", "thogayal", "pachadi"]),
    ("raita",     ["raita"]),
    ("salad",     ["salad", "kosambari", "koshimbir"]),
    ("soup",      ["soup", "rasam", "saaru", "shorba"]),
    ("refreshment", ["lassi", "juice", "sharbat", "thandai", "smoothie", "milkshake",
                     "shake", "punch", "mojito", "cooler"]),
    ("cakes",     ["cake", "cookie", "biscuit", "muffin", "brownie", "pastry"]),
    ("sweets",    ["halwa", "kheer", "payasam", "burfi", "barfi", "ladoo", "laddu",
                   "jamun", "mysore pak", "kulfi", "sweet", "pudding", "peda", "sandesh",
                   "jalebi", "modak", "obbattu", "boli", "sheera"]),
    ("daal",      ["daal", "dal ", "sambar", "sambhar", "kootu", "pappu", "lentil"]),
    ("curries",   ["curry", "korma", "kurma", "masala", "gravy", "kuzhambu", "gosht"]),
    ("snacks",    ["idli", "upma", "poha", "chaat", "tikki", "bhel", "sev", "namkeen",
                   "murukku", "chakli", "samosa", "kachori", "roll", "spring"]),
    ("paneer",    ["cheese"]),
]


def infer_category(title, text):
    """Best-guess category slug from title (then body) for orphan recipes."""
    hay = (title + " " + text).lower()
    for slug, kws in INFER_RULES:
        if any(k in hay for k in kws):
            return slug
    return "assorted"


def is_veg(primary, ingredients, method):
    if primary in NONVEG_CATS:
        return False
    blob = " ".join(ingredients + method).lower()
    meat = ("chicken", "mutton", "lamb", "beef", "pork", "fish", "prawn", "shrimp",
            "crab", "egg ", "eggs", "bacon", "ham ", "meat")
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
            dropped += 1
            continue
        rec = extract_recipe(path)
        if rec is None or not rec["title"] or rec["title"] == "Untitled":
            dropped += 1
            continue
        fname = path.name.lower()
        prim = primary.get(fname)
        if prim is None:   # not listed in any category index -> infer from the dish
            prim = infer_category(rec["title"], " ".join(rec["ingredients"][:6]))
        recipes.append({
            "id": int(re.search(r"\d+", fname).group()),
            "title": rec["title"],
            "contributor": rec["contributor"],
            "category": prim,
            "categoryName": CAT_NAME.get(prim, "Assorted"),
            "south": fname in south,
            "isVeg": is_veg(prim, rec["ingredients"], rec["method"]),
            "ingredients": rec["ingredients"],
            "method": rec["method"],
        })
    OUT.write_text(json.dumps(recipes, ensure_ascii=False), encoding="utf-8")

    by_cat = Counter(r["category"] for r in recipes)
    veg_n = sum(1 for r in recipes if r["isVeg"])
    print(f"recipes written: {len(recipes)}  (dropped {dropped})")
    print(f"vegetarian: {veg_n}   non-veg: {len(recipes) - veg_n}")
    print(f"no ingredients: {sum(1 for r in recipes if not r['ingredients'])}"
          f"   no method: {sum(1 for r in recipes if not r['method'])}")
    print("by category:", dict(sorted(by_cat.items(), key=lambda kv: -kv[1])))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
