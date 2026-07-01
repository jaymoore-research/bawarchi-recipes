import pathlib
import build_site as b

CONTRIB = pathlib.Path(__file__).parent.parent / "contribution"


def test_grilled_apple_toast_2001():
    """2001-era lowercase markup: heading font + <b>Method</b>, contributor via 'by'."""
    r = b.extract_recipe(CONTRIB / "contrib1.html")
    assert r is not None
    assert r["title"] == "Grilled Apple Toast"
    assert r["contributor"] == "Bhavana Jain"
    assert any("Bread Slices" in x for x in r["ingredients"])
    assert not any("Bread Slices" in x for x in r["method"])
    assert any("toaster" in x.lower() for x in r["method"])
    # the "Method" label must not survive as a step
    assert not any(x.strip().lower().rstrip(":") == "method" for x in r["method"])


def test_late_era_recipe_2008():
    """2008 sify-era: UPPERCASE tags, size=+1 unquoted, <B>Method:</B>, <OL><LI> steps."""
    r = b.extract_recipe(CONTRIB / "contrib5608.html")
    assert r is not None
    assert r["title"] == "Karela Fry"
    assert r["title"] != "Untitled"
    assert "bawarchi" not in r["title"].lower()
    # real recipe content, not navigation cruft
    assert any("karela" in x.lower() for x in r["ingredients"])
    assert any("seeds" in x.lower() or "cut" in x.lower() for x in r["method"])
    joined = " ".join(r["ingredients"] + r["method"]).lower()
    assert "sify" not in joined and "astrology" not in joined
    # section labels must not survive as content lines
    assert not any(x.strip().lower().rstrip(":") in ("method", "ingredients")
                   for x in r["ingredients"] + r["method"])


def test_degrades_gracefully_on_missing():
    assert b.extract_recipe(CONTRIB / "does-not-exist.html") is None
