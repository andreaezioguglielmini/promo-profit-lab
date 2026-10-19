import pandas as pd

from promolab import descriptive


def _products():
    rows = [
        # name, category, qty, price
        ("Empanadas", "Empanadas", 100, 7.0),
        ("Tacos premium", "Tacos", 30, 16.0),
        ("Crocchette", "Crocchette", 60, 8.0),
        ("Patatas", "Tapas", 50, 7.0),
        ("Tagliere", "Tapas", 2, 22.0),
        ("Insalata", "Contorni", 4, 5.0),
        ("Acqua", "Bevande", 1, 2.0),
    ]
    df = pd.DataFrame(rows, columns=["name", "category", "qty", "price"])
    df["revenue"] = df["qty"] * df["price"]
    df["period_start"] = pd.Timestamp("2026-03-03")
    df["period_end"] = pd.Timestamp("2026-03-18")
    return df


def test_tags_separate_volume_from_value():
    rows = {r["name"]: r["tag"] for r in descriptive.product_performance(_products(), top_n=6, highlighted=3)}
    assert rows["Empanadas"] == "alto volume"
    assert rows["Tacos premium"] == "alto fatturato"  # top-3 revenue with few units
    assert rows["Patatas"] == "da approfondire"


def test_low_rotation_skips_drinks_and_explains():
    low = descriptive.low_rotation(_products(), n=2)
    assert [r["name"] for r in low] == ["Tagliere", "Insalata"]
    assert low[0]["possible_reason"].startswith("prezzo elevato")


def test_trend_headlines():
    t = descriptive.sales_trend(_products())
    assert t["items_sold"] == 247
    assert t["peak_period"]["label"] == "3–18 mar"
    assert t["lead_category"] == "Empanadas"


def test_period_label_across_months():
    assert descriptive.period_label(pd.Timestamp("2026-05-22"), pd.Timestamp("2026-06-06")) == "22 mag–6 giu"


def test_open_questions_follow_available_data():
    q = descriptive.open_questions({"costs": False, "orders": True, "ads": True})
    margin = next(x for x in q if "margine" in x["question"])
    assert not margin["answerable_now"]
    assert any(x["answerable_now"] and x["tool"] == "evaluate_promo" for x in q)
