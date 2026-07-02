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
OUT = ROOT / "docs" / "recipes.json"

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
        # "assorted" is the site's own junk-drawer index; ignore it as a primary so
        # those recipes get real categories via inference. Likewise a recipe listed
        # only in the cross-cutting "south" index has no known primary.
        known = [c for c in cs if c in CAT_PRIORITY and c != "assorted"]
        primary[r] = min(known, key=lambda c: CAT_PRIORITY[c]) if known else None
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
    ("dosas",     ["dosa", "uttapam", "uttappam", "uthappam", "appam", "pesarattu", "adai",
                   "paniyaram", "vellayappam", "neer dosa", "pancake"]),
    ("pakora",    ["pakora", "pakoda", "bajji", "bonda", "vada", "vadai", "cutlet", "bhaji",
                   "kodbale", "kodubale", "nippattu", "thattai", "murukku", "chakli", "ribbon"]),
    ("rice",      ["biryani", "biriyani", "pulao", "pulav", "pongal", "fried rice",
                   "bhath", "bath", "rice", "khichdi", "kichadi", "pulihora", "puliyodarai",
                   "puliogare", "chitranna", "bisibele", "pulihara"]),
    ("roti",      ["roti", "paratha", "parantha", "naan", "chapati", "chapathi",
                   "thepla", "poori", "puri", "kulcha", "phulka"]),
    ("bread",     ["pizza", "sandwich", "toast", "burger", "bread"]),
    ("chutney",   ["chutney", "pickle", "thokku", "podi", "achar", "thogayal", "thuvaiyal",
                   "pachadi", "gojju"]),
    ("raita",     ["raita"]),
    ("salad",     ["salad", "kosambari", "koshimbir"]),
    ("soup",      ["soup", "rasam", "saaru", "saar", "shorba", "pepper water", "mulligatawny"]),
    ("refreshment", ["lassi", "juice", "sharbat", "thandai", "smoothie", "milkshake",
                     "shake", "punch", "mojito", "cooler", "buttermilk"]),
    ("cakes",     ["cake", "cookie", "biscuit", "muffin", "brownie", "pastry"]),
    ("sweets",    ["halwa", "kheer", "payasam", "payasa", "burfi", "barfi", "ladoo", "laddu",
                   "jamun", "mysore pak", "kulfi", "sweet", "pudding", "peda", "sandesh",
                   "jalebi", "modak", "obbattu", "boli", "sheera", "kozhukattai", "kozukkattai",
                   "ariselu", "poornam"]),
    ("daal",      ["daal", "dal ", "pappu", "lentil", "paruppu", "usili", "paruppu usili"]),
    ("curries",   ["curry", "korma", "kurma", "masala", "gravy", "kuzhambu", "kozhambu",
                   "kootu", "sambar", "sambhar", "kadhi", "saagu", "sagu", "pulusu",
                   "pulissery", "morkuzhambu", "mor kuzhambu", "vatha", "avial", "aviyal",
                   "gosht", "poriyal", "podimas", "thoran", "sabzi", "sabji"]),
    ("snacks",    ["idli", "upma", "uppma", "poha", "chaat", "tikki", "bhel", "sev", "namkeen",
                   "samosa", "kachori", "roll", "spring", "sevai", "tiffin", "kadabu",
                   "puttu", "noodle", "maggi", "chips", "puff", "frankie"]),
    ("paneer",    ["cheese"]),
    ("sweets",    ["ice cream", "icecream", "jello", "kesari", "kesari bath", "custard"]),
    ("vegetables", ["fry", "curry leaves", "poriyal", "palya", "subzi", "subji", "koora",
                    "keerai", "greens", "bhurta", "bhurtha", "vepudu", "vepdu"]),
    ("curries",   ["molakootal", "molagootal", "puli", "menskai", "menaskai", "gojju",
                   "kadhi", "miriam", "mudhe", "ragi", "koottu"]),
]


def infer_category(title, text):
    """Best-guess category slug from title (then body) for orphan recipes.

    Never returns 'assorted' — the final fallback is Curries, the safest home for
    an unrecognised savoury Indian dish. Callers drop true non-recipes upstream.
    """
    hay = (title + " " + text).lower()
    for slug, kws in INFER_RULES:
        if any(k in hay for k in kws):
            return slug
    return "curries"


# Sub-buckets for the big Vegetables category, matched by specificity: a
# distinctive vegetable is checked before a common one so e.g. "Baingan Aloo"
# lands in Baingan, not Aloo. (Ported from the original build-book.py.)
VEG_SUBCATS = [
    ("Karela / Bittergourd",   ["karela", "bitter gourd", "bittergourd", "pavakkai"]),
    ("Bhindi / Okra",          ["bhindi", "okra", "bendekai", "vendakkai", "behndi"]),
    ("Baingan / Eggplant",     ["baingan", "baigan", "brinjal", "eggplant", "vangi", "vankaya", "kathirikai"]),
    ("Methi & Palak (Greens)", ["methi", "palak", "spinach", "saag", "fenugreek", "amaranth", "keerai", "greens"]),
    ("Gobi / Cauliflower",     ["gobi", "gobhi", "cauliflower"]),
    ("Chole / Rajma / Chana",  ["chole", "chana", "channa", "chickpea", "rajma", "kidney bean"]),
    ("Lauki / Gourds",         ["lauki", "louki", "doodhi", "ghia", "tinda", "tindora", "parwal",
                                "turai", "ridge gourd", "bottle gourd", "snake gourd", "ash gourd",
                                "pumpkin", "kaddu"]),
    ("Yam, Plantain & Root",   ["yam", "plantain", "raw banana", "kachri", "arbi", "arvi",
                                "colocasia", "suran"]),
    ("Koftas",                 ["kofta"]),
    ("Cabbage",                ["cabbage", "patta gobi"]),
    ("Capsicum / Mirchi",      ["capsicum", "mirchi", "bell pepper"]),
    ("Matar / Peas & Beans",   ["matar", "mutter", "peas", "beans", "lobia"]),
    ("Carrot & Beetroot",      ["carrot", "gajar", "beetroot", "beet "]),
    ("Corn",                   ["corn", "makai", "makki", "bhutta"]),
    ("Tomato",                 ["tomato", "tamatar"]),
    ("Aloo / Potato",          ["aloo", "potato", "alu "]),
]
# Reading order for display (aloo/gobi/etc. first; catch-all last).
VEG_SUB_ORDER = [
    "Aloo / Potato", "Baingan / Eggplant", "Bhindi / Okra", "Gobi / Cauliflower",
    "Cabbage", "Capsicum / Mirchi", "Matar / Peas & Beans", "Chole / Rajma / Chana",
    "Methi & Palak (Greens)", "Karela / Bittergourd", "Lauki / Gourds",
    "Carrot & Beetroot", "Corn", "Tomato", "Yam, Plantain & Root", "Koftas",
    "Other Vegetables",
]


def veg_subcat(title, text):
    """Sub-category display name for a Vegetables recipe, or 'Other Vegetables'."""
    hay = (title + " " + text).lower()
    for name, kws in VEG_SUBCATS:
        if any(k in hay for k in kws):
            return name
    return "Other Vegetables"


# Sub-buckets for the vague "Regional Specialities" + "East / West / North"
# categories, by region/cuisine. Specificity order: distinctive cuisines first.
REGION_SUBCATS = [
    ("Indo-Chinese",          ["manchurian", "hakka", "schezwan", "szechuan", "szechwan",
                               "chinese", "chowmein", "chow mein", "spring roll", "hot and sour",
                               "chilli paneer", "chilli garlic"]),
    ("Italian & Continental", ["pasta", "pizza", "lasagn", "risotto", "spaghetti", "macaroni",
                               "continental", "ravioli", "gnocchi", "au gratin"]),
    ("Mexican",               ["taco", "tortilla", "salsa", "nacho", "quesadilla", "enchilada",
                               "burrito", "mexican", "fajita"]),
    ("Thai & East Asian",     ["thai", "pad thai", "tom yum", "teriyaki", "sushi", "kimchi"]),
    ("Bengali",               ["bengali", "shukto", "posto", "chorchori", "luchi", "shorshe",
                               "bhapa", "cholar", "kosha"]),
    ("Gujarati",              ["gujarati", "dhokla", "thepla", "undhiyu", "khandvi", "fafda",
                               "handvo", "khakhra", "gujarat"]),
    ("Maharashtrian",         ["maharashtrian", "misal", "thalipeeth", "puran poli", "zunka",
                               "sabudana", "kolhapuri", "amti"]),
    ("Punjabi & North",       ["punjabi", "amritsari", "chole bhature", "sarson", "makki",
                               "dhaba", "pindi"]),
    ("Rajasthani",            ["rajasthani", "gatte", "ker sangri", "dal baati", "baati"]),
    ("Kashmiri",              ["kashmiri", "rogan", "yakhni"]),
    ("Sindhi",                ["sindhi", "sai bhaji", "koki", "sindh"]),
    ("South Indian",          ["south indian", "andhra", "chettinad", "kerala", "tamil",
                               "karnataka", "udupi", "mangalorean", "hyderabadi", "malabar"]),
]
REGION_ORDER = [name for name, _ in REGION_SUBCATS] + ["Other Regional"]


def region_subcat(title, text):
    """Region/cuisine sub-name for a regional recipe, or 'Other Regional'."""
    hay = (title + " " + text).lower()
    for name, kws in REGION_SUBCATS:
        if any(k in hay for k in kws):
            return name
    return "Other Regional"


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
        # Sify-era listing/landing pages scraped as recipes: boilerplate pipe title,
        # no method. Not real recipes -> drop.
        if "|" in rec["title"] or not rec["method"] and "recipes" in rec["title"].lower():
            dropped += 1
            continue
        fname = path.name.lower()
        prim = primary.get(fname)
        if prim is None:   # not listed in any category index -> infer from the dish
            prim = infer_category(rec["title"], " ".join(rec["ingredients"][:6]))
        # Strong title corrections that beat a loose/ambiguous index listing —
        # these dishes get lumped into Snacks or Salads by the source indexes.
        tl = rec["title"].lower()
        if "raita" in tl:
            prim = "raita"
        elif any(k in tl for k in ("vada", "vadai", "bonda", "bajji", "pakora",
                                   "pakoda", "cutlet")):
            prim = "pakora"
        elif "pachadi" not in tl and ("pickle" in tl or "thokku" in tl):
            prim = "chutney"
        blurb = rec["title"] + " " + " ".join(rec["ingredients"][:6])
        sub = None
        if prim == "vegetables":
            sub = veg_subcat(rec["title"], blurb)
        elif prim in ("regional", "east"):
            sub = region_subcat(rec["title"], blurb)
        recipes.append({
            "id": int(re.search(r"\d+", fname).group()),
            "title": rec["title"],
            "contributor": rec["contributor"],
            "category": prim,
            "categoryName": CAT_NAME.get(prim, "Assorted"),
            "sub": sub,
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
