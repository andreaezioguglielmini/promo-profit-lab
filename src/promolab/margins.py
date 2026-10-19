"""Unit economics of a delivery promotion.

Implements sections 2 and 5 of docs/framework.md:

    m0      = P (1 - f) - c - g                  contribution per unit at full price
    m1(d)   = P (1 - d) (1 - f) - c - g          contribution per unit under discount d
    U*      = m0 / m1 - 1                        uplift needed to break even
    dPi     = q1 m1 - q0 m0 - kappa - F          change in contribution vs. not promoting

All money is in euros, all rates are fractions (0.20 == 20%).
"""

from __future__ import annotations

import math
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

CommissionBase = Literal["discounted", "full"]


class Dish(BaseModel):
    name: str
    category: str = "Other"
    price: float = Field(gt=0, description="Menu price paid by the customer, VAT included")
    food_cost: float = Field(ge=0)
    packaging: float = Field(default=0.0, ge=0)


def unit_margin(price: float, commission: float, food_cost: float, packaging: float = 0.0) -> float:
    """Contribution per unit sold at full price (m0)."""
    return price * (1 - commission) - food_cost - packaging


def promo_margin(
    price: float,
    discount: float,
    commission: float,
    food_cost: float,
    packaging: float = 0.0,
    commission_base: CommissionBase = "discounted",
) -> float:
    """Contribution per unit sold under a restaurant-funded discount (m1).

    `commission_base="full"` models platforms that charge commission on the
    pre-discount price, which makes every promo more expensive.
    """
    _check_rate(discount, "discount")
    paid = price * (1 - discount)
    commission_paid = commission * (paid if commission_base == "discounted" else price)
    return paid - commission_paid - food_cost - packaging


def two_for_one_margin(price: float, commission: float, food_cost: float, packaging: float = 0.0) -> float:
    """Contribution of a 2x1: the customer pays once, the kitchen cooks twice."""
    return price * (1 - commission) - 2 * (food_cost + packaging)


def breakeven_uplift(m0: float, m1: float, incrementality: float = 1.0) -> float:
    """Observed uplift needed to keep total contribution unchanged.

    With incrementality iota < 1 only part of the lift is genuinely new demand,
    so the observed lift must be U* / iota. Returns +inf when the promo margin is
    zero or negative: no volume can ever pay for it.
    """
    if not 0 < incrementality <= 1:
        raise ValueError("incrementality must be in (0, 1]")
    if m1 <= 0:
        return math.inf
    return (m0 / m1 - 1) / incrementality


def max_discount_for_floor(price: float, commission: float, food_cost: float, packaging: float, margin_floor: float) -> float:
    """Deepest discount that keeps m1 >= margin_floor (0 if even full price is below it)."""
    headroom = price * (1 - commission) - food_cost - packaging - margin_floor
    if headroom <= 0:
        return 0.0
    return min(1.0, headroom / (price * (1 - commission)))


def delta_profit(q0: float, q1: float, m0: float, m1: float, cannibalization: float = 0.0, fixed_cost: float = 0.0) -> float:
    """Change in contribution from running the promo instead of doing nothing."""
    return q1 * m1 - q0 * m0 - cannibalization - fixed_cost


def decompose_delta_profit(q0: float, q1: float, m0: float, m1: float) -> dict[str, float]:
    """Split dPi into margin earned on new volume and margin given away on existing volume."""
    earned = (q1 - q0) * m1
    given_away = q0 * (m0 - m1)
    return {"earned_on_new_orders": earned, "given_away_on_existing_orders": given_away, "net": earned - given_away}


def breakeven_table(
    menu: pd.DataFrame,
    discounts: list[float],
    commission: float,
    incrementality: float = 1.0,
    margin_floor: float = 0.0,
    commission_base: CommissionBase = "discounted",
) -> pd.DataFrame:
    """Break-even uplift for every dish and discount depth.

    `menu` needs the columns name, price, food_cost and optionally category and packaging.
    """
    rows = []
    for dish in menu.to_dict("records"):
        packaging = float(dish.get("packaging", 0.0) or 0.0)
        m0 = unit_margin(dish["price"], commission, dish["food_cost"], packaging)
        for d in discounts:
            m1 = promo_margin(dish["price"], d, commission, dish["food_cost"], packaging, commission_base)
            u = breakeven_uplift(m0, m1, incrementality)
            rows.append(
                {
                    "name": dish["name"],
                    "category": dish.get("category", "Other"),
                    "price": dish["price"],
                    "discount": d,
                    "margin_full": round(m0, 2),
                    "margin_promo": round(m1, 2),
                    "breakeven_uplift": u,
                    "below_floor": m1 < margin_floor,
                }
            )
    return pd.DataFrame(rows)


def basket_margins(
    menu: pd.DataFrame, mix: pd.Series, commission: float, discount: float, commission_base: CommissionBase = "discounted"
) -> tuple[float, float]:
    """Average contribution per order (m0, m1) for a storewide discount.

    `mix` is the expected quantity of each dish per order, indexed by dish name.
    """
    m0 = m1 = 0.0
    for dish in menu.to_dict("records"):
        qty = float(mix.get(dish["name"], 0.0))
        if qty == 0:
            continue
        packaging = float(dish.get("packaging", 0.0) or 0.0)
        m0 += qty * unit_margin(dish["price"], commission, dish["food_cost"], packaging)
        m1 += qty * promo_margin(dish["price"], discount, commission, dish["food_cost"], packaging, commission_base)
    return m0, m1


def _check_rate(x: float, name: str) -> None:
    if not 0 <= x < 1:
        raise ValueError(f"{name} must be in [0, 1), got {x}")
