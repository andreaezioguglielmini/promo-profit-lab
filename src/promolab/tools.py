"""The tools the agent can call.

Every number the agent reports has to come out of one of these functions: the
model plans and explains, the code computes. Each tool takes JSON arguments,
returns a JSON-serialisable dict, and raises ToolError with an actionable
message when the data cannot answer the question.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from promolab import ads as ads_mod
from promolab import experiments, ingest, margins
from promolab.uplift import UpliftEstimate, daily_counts, estimate_uplift

WEEKDAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
VERDICT_PROB = 0.90  # P(uplift > break-even) needed to call a promo profitable (or 1 - it, unprofitable)


class ToolError(Exception):
    """Raised when a tool cannot run; the message goes back to the model as an error result."""


@dataclass
class Workspace:
    """Parsed exports for one restaurant plus cached intermediate results."""

    data: ingest.Dataset
    default_food_cost_share: float = 0.30
    default_packaging: float = 0.50
    _cache: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_folder(cls, folder: str | Path) -> Workspace:
        return cls(ingest.load_folder(folder))

    # ---------------------------------------------------------------- helpers

    def orders(self) -> pd.DataFrame:
        if self.data.orders is None or self.data.orders.empty:
            raise ToolError("No orders export found. Ask the owner for the Deliveroo 'Ordini' CSV.")
        return self.data.orders

    def commission_rate(self) -> float:
        o = self.orders()
        paid = o["paid"].where(o["paid"] > 0)
        return float((o["commission"] / paid).median())

    def menu(self) -> tuple[pd.DataFrame, bool]:
        """Dish table with costs; second value is True when costs were assumed, not provided."""
        if self.data.costs is not None:
            return self.data.costs, False
        if self.data.products is None:
            raise ToolError("Neither a cost sheet nor product sales were found, so dish margins cannot be computed.")
        p = self.data.products.groupby(["name", "category"], as_index=False)["price"].median()
        p["food_cost"] = p["price"] * self.default_food_cost_share
        p["packaging"] = self.default_packaging
        return p, True

    def mix(self) -> pd.Series:
        """Expected quantity of each dish in an average order."""
        if self.data.products is None:
            raise ToolError("Product sales exports are missing, so the basket mix is unknown.")
        qty = self.data.products.groupby("name")["qty"].sum()
        items_per_order = qty.sum() / len(self.orders())
        return qty / qty.sum() * items_per_order

    def daily(self) -> pd.DataFrame:
        if "daily" not in self._cache:
            self._cache["daily"] = daily_counts(self.orders(), self.data.calendar)
        return self._cache["daily"]

    def uplift(self) -> UpliftEstimate:
        if "uplift" not in self._cache:
            try:
                self._cache["uplift"] = estimate_uplift(self.daily())
            except ValueError as e:
                raise ToolError(f"Cannot estimate uplift: {e}. Recommend a designed on/off test instead.") from e
        return self._cache["uplift"]

    def promo_discount(self) -> float | None:
        cal = self.data.calendar
        if cal is not None and cal["promo"].any():
            return float(cal.loc[cal["promo"], "discount"].median())
        o = self.orders()
        promo = o[o["promo"]]
        if promo.empty:
            return None
        return float((promo["discount"] / promo["subtotal"]).median())


# -------------------------------------------------------------------- tools


def inspect_data(ws: Workspace) -> dict:
    d = ws.data
    out: dict[str, Any] = {"files": d.files, "unrecognised_files": d.skipped}
    if d.orders is not None:
        o = d.orders
        out["orders"] = {"rows": int(len(o)), "first_day": str(o["date"].min().date()), "last_day": str(o["date"].max().date())}
    out["has_cost_sheet"] = d.costs is not None
    out["has_promo_calendar"] = d.calendar is not None
    out["has_ads"] = d.ads is not None
    out["has_product_sales"] = d.products is not None
    gaps = []
    if d.costs is None:
        gaps.append(f"no food cost sheet: margins will assume food cost = {ws.default_food_cost_share:.0%} of price")
    if d.calendar is None:
        gaps.append("no promo calendar: promo nights are inferred from discounted orders")
    out["gaps"] = gaps
    return out


def sales_overview(ws: Workspace) -> dict:
    o = ws.orders()
    daily = ws.daily()
    by_wd = daily.groupby("weekday")["orders"].mean()
    hours = o["submitted_at"].dt.hour.value_counts(normalize=True).sort_index()
    out = {
        "orders": int(len(o)),
        "open_nights": int(len(daily)),
        "orders_per_night": round(float(daily["orders"].mean()), 2),
        "revenue_paid_by_customers": round(float(o["paid"].sum()), 2),
        "average_order_value_before_discount": round(float(o["subtotal"].mean()), 2),
        "average_order_value_paid": round(float(o["paid"].mean()), 2),
        "share_of_orders_with_discount": round(float(o["promo"].mean()), 4),
        "estimated_commission_rate": round(ws.commission_rate(), 4),
        "orders_per_night_by_weekday": {WEEKDAYS_IT[k]: round(float(v), 2) for k, v in by_wd.items()},
        "share_of_orders_by_hour": {f"{h}:00": round(float(v), 3) for h, v in hours.items()},
    }
    if ws.data.products is not None:
        top = ws.data.products.groupby("name")["revenue"].sum().sort_values(ascending=False)
        out["top_dishes_by_revenue"] = {k: round(float(v), 2) for k, v in top.head(5).items()}
        out["share_of_revenue_top_dish"] = round(float(top.iloc[0] / top.sum()), 4)
    return out


def unit_economics(ws: Workspace, discount: float, incrementality: float = 1.0, margin_floor: float = 1.5) -> dict:
    if not 0 < discount < 1:
        raise ToolError("discount must be a fraction between 0 and 1, e.g. 0.2 for 20%")
    menu, assumed = ws.menu()
    f = ws.commission_rate()
    m0, m1 = margins.basket_margins(menu, ws.mix(), f, discount)
    aov = float(ws.orders()["subtotal"].mean())
    table = margins.breakeven_table(menu, [discount], f, incrementality, margin_floor)
    table = table.sort_values("breakeven_uplift", ascending=False)
    u = margins.breakeven_uplift(m0, m1, incrementality)
    return {
        "discount": discount,
        "commission_rate": round(f, 4),
        "costs_assumed": assumed,
        "margin_per_order_full_price": round(m0, 2),
        "margin_per_order_with_discount": round(m1, 2),
        "contribution_rate_full_price": round(m0 / aov, 4),
        "breakeven_uplift": _r(u),
        "assumed_incrementality": incrementality,
        "dishes_hardest_to_discount": _records(table.head(3), ["name", "price", "margin_full", "margin_promo", "breakeven_uplift"]),
        "dishes_easiest_to_discount": _records(table.tail(3), ["name", "price", "margin_full", "margin_promo", "breakeven_uplift"]),
        "dishes_below_margin_floor": table.loc[table["below_floor"], "name"].tolist(),
        "margin_floor": margin_floor,
    }


def estimate_promo_uplift(ws: Workspace) -> dict:
    est = ws.uplift()
    out = est.to_dict()
    out["interval_level"] = 0.90
    out["note"] = (
        "Uplift is the change in orders per open night on promo nights vs. comparable non-promo nights, "
        "controlling for weekday and a linear trend."
    )
    return out


def evaluate_promo(ws: Workspace, discount: float | None = None, incrementality: float = 1.0) -> dict:
    if discount is None:
        discount = ws.promo_discount()
        if discount is None:
            raise ToolError("No discounted orders found; pass the discount to evaluate explicitly.")
    econ = unit_economics(ws, discount, incrementality)
    est = ws.uplift()
    m0, m1 = econ["margin_per_order_full_price"], econ["margin_per_order_with_discount"]
    u_star = margins.breakeven_uplift(m0, m1, incrementality)
    p = est.prob_above(u_star)
    base = est.mean_orders_control

    def per_night(u: float) -> float:
        return round(margins.delta_profit(base, base * (1 + u), m0, m1), 2)

    if p >= VERDICT_PROB:
        verdict = "profitable"
    elif p <= 1 - VERDICT_PROB:
        verdict = "unprofitable"
    else:
        verdict = "inconclusive"
    return {
        "discount": round(discount, 4),
        "verdict": verdict,
        "probability_promo_beats_breakeven": round(p, 3),
        "breakeven_uplift": _r(u_star),
        "estimated_uplift": round(est.uplift, 4),
        "uplift_interval_90": [round(est.ci_low, 4), round(est.ci_high, 4)],
        "orders_per_night_without_promo": round(base, 2),
        "margin_per_order_full_price": m0,
        "margin_per_order_with_discount": m1,
        "profit_change_per_promo_night": per_night(est.uplift),
        "profit_change_per_promo_night_interval_90": [per_night(est.ci_low), per_night(est.ci_high)],
        "promo_nights_observed": est.promo_days,
        "profit_change_over_observed_promo_nights": round(per_night(est.uplift) * est.promo_days, 2),
        "costs_assumed": econ["costs_assumed"],
        "decision_rule": f"profitable if P(uplift > break-even) >= {VERDICT_PROB}, unprofitable if <= {1 - VERDICT_PROB:.2f}",
    }


def plan_experiment(ws: Workspace, target_uplift: float | None = None, alpha: float = 0.10, power: float = 0.80) -> dict:
    daily = ws.daily()
    base = float(daily.loc[~daily["promo"], "orders"].mean()) if (~daily["promo"]).any() else float(daily["orders"].mean())
    if target_uplift is None:
        d = ws.promo_discount() or 0.2
        econ = unit_economics(ws, d)
        target_uplift = econ["breakeven_uplift"]
        if not target_uplift or math.isinf(target_uplift):
            raise ToolError("The promo can never break even at this discount; test a shallower discount instead.")
    disp = ws.uplift().dispersion if "uplift" in ws._cache else 1.5
    # Convert quasi-Poisson dispersion phi to gamma shape r: Var = l + l^2/r = phi * l  =>  r = l / (phi - 1)
    r = base / (disp - 1) if disp > 1.0001 else 1e6
    n = experiments.nights_per_arm(base, target_uplift, r, alpha, power)
    open_per_week = len(set(daily["weekday"]))
    start = daily["date"].max() + timedelta(days=1)
    schedule = experiments.switchback_schedule(start.date(), n, sorted(set(daily["weekday"])))
    observed_per_arm = int(min(daily["promo"].sum(), (~daily["promo"]).sum()))
    return {
        "target_uplift": _r(target_uplift),
        "baseline_orders_per_night": round(base, 2),
        "nights_per_arm": n,
        "total_open_nights": 2 * n,
        "weeks_needed": round(2 * n / open_per_week, 1),
        "significance_alpha": alpha,
        "power": power,
        "minimum_detectable_uplift_with_current_data": _r(
            experiments.minimum_detectable_uplift(base, observed_per_arm, r, alpha, power) if observed_per_arm else math.inf
        ),
        "first_two_weeks_schedule": [
            {"date": str(row.date), "promo": bool(row.promo)} for row in schedule.head(2 * open_per_week).itertuples()
        ],
        "design": "switchback: promo on/off on alternating same-weekday nights, randomised within each pair",
    }


def evaluate_ads(ws: Workspace, incrementality: float = 0.5) -> dict:
    if ws.data.ads is None:
        raise ToolError("No ads export found.")
    econ = unit_economics(ws, 0.1)
    return ads_mod.evaluate_ads(ws.data.ads, econ["contribution_rate_full_price"], incrementality)


# ------------------------------------------------------------- tool schemas


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: Callable[..., dict]

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


_RATE = {"type": "number", "description": "fraction, e.g. 0.2 for 20%"}

TOOLS: list[Tool] = [
    Tool(
        "inspect_data",
        "List the exports that were loaded, their date range, and which inputs are missing. Call this first.",
        _obj({}),
        inspect_data,
    ),
    Tool(
        "sales_overview",
        "Orders, revenue, average order value, share of discounted orders, orders per night by weekday and hour, top dishes.",
        _obj({}),
        sales_overview,
    ),
    Tool(
        "unit_economics",
        "Margin per order at full price and with a discount, the break-even uplift (extra orders needed to not lose money) and which dishes are hardest to discount.",
        _obj(
            {
                "discount": _RATE,
                "incrementality": {"type": "number", "description": "share of the lift that is genuinely new demand (0-1], default 1"},
            },
            ["discount"],
        ),
        unit_economics,
    ),
    Tool(
        "estimate_promo_uplift",
        "Estimate how much promo nights lifted orders vs. comparable nights, with a 90% interval. Fails if there are too few promo or non-promo nights.",
        _obj({}),
        estimate_promo_uplift,
    ),
    Tool(
        "evaluate_promo",
        "Verdict on the promo: compares the estimated uplift with the break-even uplift and gives the profit change per promo night in euros. Omit discount to use the one in the data.",
        _obj({"discount": _RATE, "incrementality": {"type": "number"}}),
        evaluate_promo,
    ),
    Tool(
        "plan_experiment",
        "How many open nights of a promo on/off test are needed to detect a target uplift (default: the break-even uplift), plus a randomised schedule.",
        _obj({"target_uplift": _RATE, "alpha": {"type": "number"}, "power": {"type": "number"}}),
        plan_experiment,
    ),
    Tool(
        "evaluate_ads",
        "Return on ad spend vs. the ROAS needed to break even given the restaurant's margin.",
        _obj(
            {"incrementality": {"type": "number", "description": "share of ad-attributed orders that are truly incremental, default 0.5"}}
        ),
        evaluate_ads,
    ),
]

SUBMIT_REPORT = {
    "name": "submit_report",
    "description": (
        "Submit the final report. Call exactly once, at the end. Every number in report_markdown must appear in a tool result "
        "(rounding is fine); the call is rejected and returned to you if it does not."
    ),
    "input_schema": _obj(
        {
            "verdict": {"type": "string", "enum": ["profitable", "unprofitable", "inconclusive"]},
            "estimated_uplift": {"type": ["number", "null"]},
            "recommendation": {"type": "string", "enum": ["keep_promo", "stop_promo", "run_experiment", "change_discount"]},
            "experiment_nights": {"type": ["integer", "null"], "description": "total open nights of the recommended test, if any"},
            "report_markdown": {"type": "string", "description": "the report for the owner"},
        },
        ["verdict", "estimated_uplift", "recommendation", "experiment_nights", "report_markdown"],
    ),
    "strict": True,
}

TOOL_INDEX = {t.name: t for t in TOOLS}


def tool_specs() -> list[dict]:
    return [t.spec() for t in TOOLS] + [SUBMIT_REPORT]


def run_tool(ws: Workspace, name: str, args: dict) -> dict:
    if name not in TOOL_INDEX:
        raise ToolError(f"unknown tool {name}")
    clean = {k: v for k, v in (args or {}).items() if v is not None}
    return TOOL_INDEX[name].fn(ws, **clean)


def _r(x: float) -> float | None:
    """Round, mapping infinity to None so results stay valid JSON."""
    return None if x is None or math.isinf(x) else round(float(x), 4)


def _records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    out = []
    for row in df[cols].to_dict("records"):
        out.append({k: (_r(v) if isinstance(v, float) else v) for k, v in row.items()})
    return out
