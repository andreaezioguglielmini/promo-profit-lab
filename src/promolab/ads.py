"""Judge paid placement (ads) against the ROAS needed to break even.

An ad euro pays off only if the contribution of the orders it brings exceeds it:

    breakeven ROAS = 1 / contribution rate,  contribution rate = margin per order / order value

With a 35% contribution rate you need ROAS above 2.9x just to stand still.
"""

from __future__ import annotations

import pandas as pd


def breakeven_roas(contribution_rate: float) -> float:
    if contribution_rate <= 0:
        return float("inf")
    return 1 / contribution_rate


def evaluate_ads(ads: pd.DataFrame, contribution_rate: float, incrementality: float = 0.5) -> dict:
    """Summarise ad spend; `incrementality` is the share of ad-attributed orders that would not have happened anyway."""
    spend = float(ads["spend"].sum())
    sales = float(ads["sales"].sum())
    roas = sales / spend if spend else 0.0
    need = breakeven_roas(contribution_rate)
    contribution = sales * contribution_rate * incrementality
    weekly = ads.assign(week=pd.to_datetime(ads["date"]).dt.to_period("W").astype(str)).groupby("week")[["spend", "sales"]].sum()
    weekly["roas"] = (weekly["sales"] / weekly["spend"]).where(weekly["spend"] > 0)
    return {
        "days": int(len(ads)),
        "spend": round(spend, 2),
        "attributed_sales": round(sales, 2),
        "attributed_orders": int(ads["orders"].sum()),
        "roas": round(roas, 2),
        "breakeven_roas": round(need, 2),
        "breakeven_roas_if_partly_incremental": round(need / incrementality, 2),
        "assumed_incrementality": incrementality,
        "estimated_net_contribution": round(contribution - spend, 2),
        "weeks_below_breakeven": int((weekly["roas"] < need / incrementality).sum()),
        "weeks": int(len(weekly)),
    }
