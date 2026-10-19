"""The descriptive analyses from the report we used to deliver by hand.

Before the agent, each pilot restaurant received a "delivery performance report"
built from the product-sales exports, in this order:

1. Summary: total revenue, items sold, revenue per item, best and worst fortnight,
   how concentrated sales are in a few categories and dishes.
2. Sales trend: revenue and items per fortnight, peak vs. weakest window.
3. Menu mix: share of revenue by category.
4. Product performance: the top dishes, tagged "alto volume" (sell many),
   "alto fatturato" (earn a lot with fewer units) or "da approfondire".
5. Low-rotation dishes (drinks excluded), each with a possible explanation to check.
6. Open questions, and the data each one needs.

This module reproduces those analyses so the agent's report starts from the same
ground the owners already knew, then goes further where the data allows.
"""

from __future__ import annotations

import pandas as pd

MONTHS_IT = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
DRINK_CATEGORIES = {"bevande", "drinks", "bibite", "vini", "birre"}


def period_label(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """'3–18 mar', or '22 mag–6 giu' across months."""
    if pd.isna(start) or pd.isna(end):
        return "periodo non indicato"
    if start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS_IT[end.month - 1]}"
    return f"{start.day} {MONTHS_IT[start.month - 1]}–{end.day} {MONTHS_IT[end.month - 1]}"


def sales_trend(products: pd.DataFrame) -> dict:
    """Chapters 1-2: headline numbers and revenue per fortnight."""
    per = (
        products.groupby(["period_start", "period_end"], dropna=False)
        .agg(revenue=("revenue", "sum"), items=("qty", "sum"))
        .reset_index()
        .sort_values("period_start")
    )
    per["label"] = [period_label(a, b) for a, b in zip(per["period_start"], per["period_end"], strict=True)]
    peak = per.loc[per["revenue"].idxmax()]
    low = per.loc[per["revenue"].idxmin()]
    total, items = float(products["revenue"].sum()), int(products["qty"].sum())
    by_cat = products.groupby("category")["revenue"].sum().sort_values(ascending=False)
    by_dish = products.groupby("name")["revenue"].sum().sort_values(ascending=False)
    return {
        "total_revenue": round(total, 2),
        "items_sold": items,
        "revenue_per_item": round(total / items, 2),
        "note_revenue_per_item": "average revenue per dish sold, not the average order value",
        "periods": int(len(per)),
        "average_revenue_per_period": round(float(per["revenue"].mean()), 2),
        "peak_period": {"label": peak["label"], "revenue": round(float(peak["revenue"]), 2)},
        "weakest_period": {"label": low["label"], "revenue": round(float(low["revenue"]), 2)},
        "peak_minus_weakest": round(float(peak["revenue"] - low["revenue"]), 2),
        "top5_categories_share": round(float(by_cat.head(5).sum() / total), 4),
        "top5_dishes_share": round(float(by_dish.head(5).sum() / total), 4),
        "lead_category": by_cat.index[0],
        "by_period": [{"label": r.label, "revenue": round(float(r.revenue), 2), "items": int(r["items"])} for _, r in per.iterrows()],
    }


def menu_mix(products: pd.DataFrame) -> list[dict]:
    """Chapter 3: revenue share and items by category."""
    cat = products.groupby("category").agg(revenue=("revenue", "sum"), items=("qty", "sum")).sort_values("revenue", ascending=False)
    total = cat["revenue"].sum()
    return [
        {
            "category": c,
            "revenue_share": round(float(r.revenue / total), 4),
            "revenue": round(float(r.revenue), 2),
            "items": int(r["items"]),
        }
        for c, r in cat.iterrows()
    ]


def product_performance(products: pd.DataFrame, top_n: int = 15, highlighted: int = 6) -> list[dict]:
    """Chapter 4: top dishes by revenue, tagged by how they earn.

    Among the `highlighted` best earners, a dish that is also among the most sold is
    "alto volume"; one that earns a lot with fewer units is "alto fatturato".
    The rest of the top list is "da approfondire".
    """
    dish = (
        products.groupby(["name", "category"])
        .agg(items=("qty", "sum"), revenue=("revenue", "sum"), price=("price", "median"))
        .reset_index()
        .sort_values("revenue", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    total = products["revenue"].sum()
    volume_rank = dish["items"].rank(ascending=False, method="first")
    rows = []
    for i, r in dish.iterrows():
        if i < highlighted:
            tag = "alto volume" if volume_rank[i] <= highlighted else "alto fatturato"
        else:
            tag = "da approfondire"
        rows.append(
            {
                "name": r["name"],
                "category": r["category"],
                "items": int(r["items"]),
                "revenue": round(float(r["revenue"]), 2),
                "revenue_share": round(float(r["revenue"] / total), 4),
                "tag": tag,
            }
        )
    return rows


def low_rotation(products: pd.DataFrame, n: int = 8) -> list[dict]:
    """Chapter 5: the least-sold food dishes, with a hypothesis to check (not a verdict)."""
    food = products[~products["category"].str.lower().isin(DRINK_CATEGORIES)]
    dish = (
        food.groupby(["name", "category"])
        .agg(items=("qty", "sum"), revenue=("revenue", "sum"), price=("price", "median"))
        .reset_index()
        .sort_values(["items", "revenue"])
    )
    expensive = dish["price"].quantile(0.75)
    rows = []
    for _, r in dish.head(n).iterrows():
        if r["price"] >= expensive:
            why = "prezzo elevato per il delivery"
        elif r["items"] <= 2:
            why = "domanda bassa, forse poca visibilità nel menu"
        else:
            why = "poco visibile o nome poco chiaro nell'app"
        rows.append(
            {
                "name": r["name"],
                "category": r["category"],
                "items": int(r["items"]),
                "revenue": round(float(r["revenue"]), 2),
                "price": round(float(r["price"]), 2),
                "possible_reason": why,
            }
        )
    return rows


# Chapter 6-7: the questions the hand-made report left open, and what unlocks them.
OPEN_QUESTIONS = [
    ("Quali piatti generano più margine, non solo più fatturato?", "food cost per piatto e commissione", "costs", "unit_economics"),
    ("La promo fa guadagnare o porta solo volume scontato?", "ordini con data, ora e sconto, calendario promo", "orders", "evaluate_promo"),
    ("In quali sere o fasce orarie una promo avrebbe senso?", "orario di ogni ordine", "orders", "sales_overview"),
    ("Gli annunci a pagamento si ripagano?", "export annunci", "ads", "evaluate_ads"),
    ("Le promo portano clienti nuovi o scontano clienti abituali?", "ID cliente anonimo per ordine", None, None),
    ("Quali piatti funzionano meglio su Deliveroo che su Glovo?", "export separati per piattaforma", None, None),
    ("Quali piatti si vendono insieme (bundle naturali)?", "righe di ogni singolo ordine", None, None),
]


def open_questions(available: dict[str, bool]) -> list[dict]:
    out = []
    for question, needs, key, tool in OPEN_QUESTIONS:
        ok = key is not None and available.get(key, False)
        out.append({"question": question, "needs": needs, "answerable_now": ok, "tool": tool if ok else None})
    return out
