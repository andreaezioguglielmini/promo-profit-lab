"""Synthetic delivery restaurants with a known promo effect.

The generator is calibrated on aggregate patterns from a real pilot (a small
tapas restaurant in Milan, dinner-only delivery, roughly 3-4 orders a night,
Friday and Saturday strongest, 19-21h peak). No real order, price list or
commission from the pilot is used: the menu, costs and every order below are
invented. Because the true uplift is a parameter, the analysis tools and the
agent can be scored against ground truth (see promolab.evals).

Outputs mimic the Italian Deliveroo Partner Hub exports so the same ingest
code path handles real and synthetic data.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from promolab import margins

# Generic tapas menu: name, category, price, food cost share of price, packaging.
DEFAULT_MENU: list[tuple[str, str, float, float, float]] = [
    ("Empanadas di manzo", "Empanadas", 7.0, 0.28, 0.40),
    ("Empanadas di pollo", "Empanadas", 8.0, 0.27, 0.40),
    ("Empanadas di verdure", "Empanadas", 6.5, 0.22, 0.40),
    ("Empanadas al prosciutto iberico", "Empanadas", 8.5, 0.38, 0.40),
    ("Crocchette di prosciutto", "Crocchette", 8.0, 0.30, 0.50),
    ("Crocchette di chorizo", "Crocchette", 8.0, 0.29, 0.50),
    ("Patatas bravas", "Tapas classiche", 7.0, 0.18, 0.60),
    ("Tortilla di patate", "Tapas classiche", 8.0, 0.20, 0.60),
    ("Calamari fritti", "Tapas classiche", 9.0, 0.33, 0.60),
    ("Polpette al sugo", "Tapas classiche", 12.0, 0.31, 0.70),
    ("Polpo alla piastra", "Tapas della casa", 18.0, 0.42, 0.80),
    ("Tataki di tonno", "Tapas della casa", 14.0, 0.40, 0.80),
    ("Montaditos burger", "Montaditos", 10.0, 0.32, 0.60),
    ("Montaditos di maiale iberico", "Montaditos", 14.0, 0.38, 0.60),
    ("Tacos di pollo", "Tacos", 13.0, 0.30, 0.70),
    ("Tacos di manzo", "Tacos", 15.0, 0.36, 0.70),
    ("Chips di zucchine", "Contorni", 5.0, 0.15, 0.40),
    ("Pimientos alla piastra", "Contorni", 5.0, 0.20, 0.40),
    ("Cheesecake", "Dolci", 7.0, 0.22, 0.40),
    ("Churros con cioccolato", "Dolci", 7.5, 0.18, 0.40),
    ("Sangria (50 cl)", "Bevande", 9.0, 0.15, 0.30),
    ("Acqua naturale", "Bevande", 2.0, 0.15, 0.10),
]

# Relative popularity of each dish, same order as DEFAULT_MENU.
DEFAULT_POPULARITY = [
    16,
    7,
    4,
    10,
    9,
    3,
    6,
    5,
    3,
    2,
    2,
    2,
    6,
    2,
    5,
    4,
    7,
    3,
    2,
    4,
    2,
    3,
]

# Mean orders per open night by weekday (Mon=0). Monday closed.
DEFAULT_WEEKDAY_RATE = {0: 0.0, 1: 2.4, 2: 2.6, 3: 3.4, 4: 4.6, 5: 4.8, 6: 2.8}

# Share of orders by hour of submission.
DEFAULT_HOURS = {17: 0.04, 18: 0.15, 19: 0.27, 20: 0.33, 21: 0.17, 22: 0.04}


@dataclass
class RestaurantConfig:
    name: str = "La Tasca Sintetica"
    start: date = date(2026, 3, 3)
    days: int = 140
    commission: float = 0.25
    vat_on_commission: float = 0.22
    weekday_rate: dict[int, float] = field(default_factory=lambda: dict(DEFAULT_WEEKDAY_RATE))
    dispersion: float = 6.0  # gamma shape for nightly demand; lower = noisier nights
    trend_per_week: float = 0.0  # multiplicative demand drift per week
    items_per_order: float = 4.6  # mean items in a basket (min 1)
    # Promo design
    promo_discount: float = 0.20
    true_uplift: float = 0.35
    promo_schedule: str = "switchback"  # "switchback", "block" or "none"
    promo_share_days: float = 0.5
    # Ads
    ads_daily_budget: float = 15.0
    ads_cpc: float = 0.75
    ads_click_to_order: float = 0.06
    seed: int = 7


@dataclass
class GroundTruth:
    restaurant: str
    promo_discount: float
    true_uplift: float
    commission: float
    margin_per_order_full: float
    margin_per_order_promo: float
    breakeven_uplift: float
    expected_orders_per_promo_day_without_promo: float
    expected_delta_profit_per_promo_day: float
    promo_is_profitable: bool
    promo_days: int
    total_days: int


def default_menu() -> pd.DataFrame:
    rows = [
        {"name": n, "category": c, "price": p, "food_cost": round(p * share, 2), "packaging": pkg} for n, c, p, share, pkg in DEFAULT_MENU
    ]
    return pd.DataFrame(rows)


def promo_days(cfg: RestaurantConfig, open_days: list[date], rng: np.random.Generator) -> set[date]:
    if cfg.promo_schedule == "none" or cfg.promo_discount == 0:
        return set()
    if cfg.promo_schedule == "block":
        # Promo runs in the last part of the period: the typical "we turned it on in May" case.
        k = int(round(len(open_days) * cfg.promo_share_days))
        return set(open_days[len(open_days) - k :])
    if cfg.promo_schedule == "switchback":
        # Randomize on/off within each weekday so weekday mix is balanced.
        on: set[date] = set()
        for wd in range(7):
            days = [d for d in open_days if d.weekday() == wd]
            k = int(round(len(days) * cfg.promo_share_days))
            on.update(rng.choice(np.array(days, dtype=object), size=k, replace=False).tolist())
        return on
    raise ValueError(f"unknown promo_schedule {cfg.promo_schedule!r}")


def simulate(cfg: RestaurantConfig, menu: pd.DataFrame | None = None, popularity: list[float] | None = None) -> dict:
    """Simulate one restaurant. Returns orders, order lines, ads, menu and ground truth."""
    rng = np.random.default_rng(cfg.seed)
    menu = default_menu() if menu is None else menu.reset_index(drop=True)
    pop = np.asarray(popularity or DEFAULT_POPULARITY[: len(menu)], dtype=float)
    pop = pop / pop.sum()

    calendar = [cfg.start + timedelta(days=i) for i in range(cfg.days)]
    open_days = [d for d in calendar if cfg.weekday_rate.get(d.weekday(), 0) > 0]
    on_days = promo_days(cfg, open_days, rng)

    hours = np.array(list(DEFAULT_HOURS))
    hour_p = np.array(list(DEFAULT_HOURS.values()))
    hour_p = hour_p / hour_p.sum()

    orders, lines, ads = [], [], []
    order_id = 1000
    for d in open_days:
        week = (d - cfg.start).days / 7
        base = cfg.weekday_rate[d.weekday()] * (1 + cfg.trend_per_week) ** week
        is_promo = d in on_days
        lam = base * (1 + cfg.true_uplift if is_promo else 1)
        # Gamma-Poisson: nights are noisier than Poisson, as in real delivery data.
        n = rng.poisson(rng.gamma(cfg.dispersion, lam / cfg.dispersion))
        discount = cfg.promo_discount if is_promo else 0.0
        for _ in range(n):
            order_id += int(rng.integers(1, 40))
            k = 1 + rng.poisson(cfg.items_per_order - 1)
            picks = rng.choice(len(menu), size=k, p=pop)
            subtotal = float(menu.loc[picks, "price"].sum())
            paid = round(subtotal * (1 - discount), 2)
            commission = round(paid * cfg.commission, 2)
            h = int(rng.choice(hours, p=hour_p))
            minute, second = int(rng.integers(0, 60)), int(rng.integers(0, 60))
            submitted = pd.Timestamp(d) + pd.Timedelta(hours=h, minutes=minute, seconds=second)
            delivered = submitted + pd.Timedelta(minutes=int(rng.integers(22, 48)))
            orders.append(
                {
                    "order_id": order_id,
                    "submitted_at": submitted,
                    "delivered_at": delivered,
                    "status": "Completato",
                    "subtotal": subtotal,
                    "discount": round(subtotal - paid, 2),
                    "paid": paid,
                    "commission": commission,
                    "vat_on_commission": round(commission * cfg.vat_on_commission, 2),
                }
            )
            for i in picks:
                lines.append(
                    {
                        "order_id": order_id,
                        "date": d,
                        "name": menu.at[i, "name"],
                        "category": menu.at[i, "category"],
                        "price": menu.at[i, "price"],
                    }
                )
        clicks = rng.poisson(cfg.ads_daily_budget / cfg.ads_cpc)
        ad_orders = rng.binomial(clicks, cfg.ads_click_to_order)
        ads.append(
            {
                "date": d,
                "clicks": int(clicks),
                "views": int(clicks * rng.uniform(9, 14)),
                "spend": round(clicks * cfg.ads_cpc, 2),
                "orders": int(ad_orders),
                "sales": round(ad_orders * rng.normal(40, 8), 2) if ad_orders else 0.0,
            }
        )

    calendar = pd.DataFrame(
        {
            "date": open_days,
            "promo": [d in on_days for d in open_days],
            "discount": [cfg.promo_discount if d in on_days else 0.0 for d in open_days],
        }
    )
    orders_df = pd.DataFrame(orders)
    lines_df = pd.DataFrame(lines)
    truth = ground_truth(cfg, menu, pop, open_days, on_days)
    return {
        "config": cfg,
        "menu": menu,
        "orders": orders_df,
        "lines": lines_df,
        "ads": pd.DataFrame(ads),
        "calendar": calendar,
        "truth": truth,
    }


def ground_truth(cfg: RestaurantConfig, menu: pd.DataFrame, pop: np.ndarray, open_days: list[date], on_days: set[date]) -> GroundTruth:
    mix = pd.Series(pop * cfg.items_per_order, index=menu["name"])
    m0, m1 = margins.basket_margins(menu, mix, cfg.commission, cfg.promo_discount)
    u_star = margins.breakeven_uplift(m0, m1)
    base = float(np.mean([cfg.weekday_rate[d.weekday()] for d in on_days])) if on_days else 0.0
    dpi = margins.delta_profit(base, base * (1 + cfg.true_uplift), m0, m1)
    return GroundTruth(
        restaurant=cfg.name,
        promo_discount=cfg.promo_discount,
        true_uplift=cfg.true_uplift,
        commission=cfg.commission,
        margin_per_order_full=round(m0, 2),
        margin_per_order_promo=round(m1, 2),
        breakeven_uplift=round(u_star, 4),
        expected_orders_per_promo_day_without_promo=round(base, 3),
        expected_delta_profit_per_promo_day=round(dpi, 2),
        promo_is_profitable=bool(cfg.true_uplift > u_star),
        promo_days=len(on_days),
        total_days=len(open_days),
    )


# ---------------------------------------------------------------- export format


def write_exports(sim: dict, out_dir: str | Path, period_days: int = 16) -> Path:
    """Write the simulation as Deliveroo-style Italian CSV exports plus a cost sheet."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg: RestaurantConfig = sim["config"]
    o = sim["orders"]

    orders_export = pd.DataFrame(
        {
            "Nome del ristorante": cfg.name,
            "Numero d'ordine": o["order_id"],
            "Stato dell'ordine": o["status"],
            "Data di invio": o["submitted_at"].dt.strftime("%Y-%m-%d"),
            "Orario di invio": o["submitted_at"].dt.strftime("%H:%M:%S"),
            "Data di consegna": o["delivered_at"].dt.strftime("%Y-%m-%d"),
            "Orario di consegna": o["delivered_at"].dt.strftime("%H:%M:%S"),
            "Subtotale": o["subtotal"],
            "Sconto offerte": o["discount"],
            "Commissione Deliveroo": o["commission"],
            "IVA su commissione Deliveroo": o["vat_on_commission"],
        }
    )
    orders_export.to_csv(out / "ordini.csv", index=False)

    # Product sales per fixed period, like the "prodotti più venduti" export.
    lines = sim["lines"].copy()
    start = pd.Timestamp(cfg.start)
    lines["period"] = ((pd.to_datetime(lines["date"]) - start).dt.days // period_days).astype(int)
    for p, chunk in lines.groupby("period"):
        a = start + pd.Timedelta(days=int(p) * period_days)
        b = a + pd.Timedelta(days=period_days - 1)
        agg = chunk.groupby(["category", "name", "price"]).size().reset_index(name="qty")
        export = pd.DataFrame(
            {
                "Nome del ristorante": cfg.name,
                "Categoria": agg["category"],
                "Nome articolo": agg["name"],
                "Quantità": agg["qty"],
                "Prezzo": agg["price"],
                "Subtotale": agg["qty"] * agg["price"],
            }
        ).sort_values("Quantità", ascending=False)
        export.to_csv(out / f"vendite_prodotti_{a:%Y-%m-%d}_{b:%Y-%m-%d}.csv", index=False)

    ads = sim["ads"]
    ads_export = pd.DataFrame(
        {
            "Date": pd.to_datetime(ads["date"]).dt.strftime("%Y-%m-%d"),
            "Data Status": "FINAL",
            "Campaign Name": "",
            "Campaign ID": "synthetic-campaign",
            "Campaign Status": "CAMPAIGN_STATUS_LIVE",
            "Punto vendita": cfg.name,
            "Total Clicks": ads["clicks"],
            "Total Views": ads["views"],
            "Total Ad Spend": ads["spend"],
            "Total Sales (clicks)": ads["sales"],
            "Total Orders (clicks)": ads["orders"],
        }
    )
    ads_export.to_csv(out / "annunci.csv", index=False)

    cal = sim["calendar"]
    pd.DataFrame(
        {
            "Data": pd.to_datetime(cal["date"]).dt.strftime("%Y-%m-%d"),
            "Promo attiva": cal["promo"].map({True: "si", False: "no"}),
            "Sconto": cal["discount"],
        }
    ).to_csv(out / "calendario_promo.csv", index=False)

    sim["menu"].rename(
        columns={"name": "Nome articolo", "category": "Categoria", "price": "Prezzo", "food_cost": "Food cost", "packaging": "Packaging"}
    ).to_csv(out / "costi_menu.csv", index=False)

    (out / "ground_truth.json").write_text(json.dumps(asdict(sim["truth"]), indent=2))
    return out


def scenario_grid(seed: int = 0) -> list[RestaurantConfig]:
    """Restaurants used by the eval suite: profitable, unprofitable, borderline and underpowered cases."""
    cases = [
        # (name, discount, true uplift, days, schedule, demand multiplier)
        ("Tasca A", 0.10, 0.45, 140, "switchback", 1.0),
        ("Tasca B", 0.20, 0.10, 140, "switchback", 1.0),
        ("Tasca C", 0.20, 0.90, 140, "switchback", 1.0),
        ("Tasca D", 0.30, 0.40, 140, "switchback", 1.0),
        ("Tasca E", 0.15, 0.30, 56, "switchback", 1.0),
        ("Tasca F", 0.20, 0.00, 140, "block", 1.0),
        ("Tasca G", 0.10, 0.25, 140, "switchback", 2.5),
        ("Tasca H", 0.25, 1.20, 140, "switchback", 1.0),
        ("Tasca I", 0.20, 0.50, 28, "switchback", 1.0),
        ("Tasca J", 0.30, 0.95, 140, "switchback", 2.0),
        ("Tasca K", 0.20, 0.40, 84, "none", 1.0),
        ("Tasca L", 0.15, 0.80, 140, "switchback", 1.0),
    ]
    out = []
    for i, (name, d, u, days, schedule, mult) in enumerate(cases):
        rates = {k: v * mult for k, v in DEFAULT_WEEKDAY_RATE.items()}
        out.append(
            RestaurantConfig(
                name=name, promo_discount=d, true_uplift=u, days=days, promo_schedule=schedule, weekday_rate=rates, seed=seed * 100 + i
            )
        )
    return out
