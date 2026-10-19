"""Plan an on/off promo test that can actually detect the effect.

For nightly counts with mean lambda and gamma-Poisson overdispersion (shape r),
the variance of log(mean count) over n nights is about (1/lambda + 1/r) / n.
Comparing promo vs. control nights on the log scale gives the nights needed per arm:

    n = (z_{1-a/2} + z_{power})^2 * [(1/l0 + 1/r) + (1/l1 + 1/r)] / log(1 + u)^2

`simulate_power` checks the formula by Monte Carlo with the same estimator the
analysis uses.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import NormalDist

import numpy as np
import pandas as pd

from promolab.uplift import estimate_uplift

_Z = NormalDist()


def nights_per_arm(base_rate: float, uplift: float, dispersion: float = 6.0, alpha: float = 0.10, power: float = 0.80) -> int:
    """Open nights needed in each arm (promo on / off) to detect `uplift`."""
    if uplift <= 0:
        raise ValueError("uplift must be positive")
    l0, l1 = base_rate, base_rate * (1 + uplift)
    var = (1 / l0 + 1 / dispersion) + (1 / l1 + 1 / dispersion)
    z = _Z.inv_cdf(1 - alpha / 2) + _Z.inv_cdf(power)
    return math.ceil(z**2 * var / math.log1p(uplift) ** 2)


def minimum_detectable_uplift(base_rate: float, nights: int, dispersion: float = 6.0, alpha: float = 0.10, power: float = 0.80) -> float:
    """Smallest uplift detectable with `nights` per arm (bisection on nights_per_arm)."""
    lo, hi = 1e-4, 20.0
    if nights_per_arm(base_rate, hi, dispersion, alpha, power) > nights:
        return math.inf
    for _ in range(60):
        mid = (lo + hi) / 2
        if nights_per_arm(base_rate, mid, dispersion, alpha, power) <= nights:
            hi = mid
        else:
            lo = mid
    return hi


def switchback_schedule(start: date, nights_each: int, open_weekdays: list[int], seed: int = 0) -> pd.DataFrame:
    """Pre-committed calendar alternating promo on/off, balanced within each weekday."""
    rng = np.random.default_rng(seed)
    days: list[date] = []
    d = start
    while len(days) < 2 * nights_each:
        if d.weekday() in open_weekdays:
            days.append(d)
        d += timedelta(days=1)
    # Pair consecutive same-weekday nights and randomise which one gets the promo.
    promo = {}
    for wd in open_weekdays:
        same = [x for x in days if x.weekday() == wd]
        for i in range(0, len(same), 2):
            pair = same[i : i + 2]
            on = rng.integers(len(pair))
            for j, x in enumerate(pair):
                promo[x] = j == on
    return pd.DataFrame({"date": days, "promo": [promo[x] for x in days]})


def simulate_power(
    base_rate: float, uplift: float, nights_each: int, dispersion: float = 6.0, alpha: float = 0.10, sims: int = 400, seed: int = 0
) -> float:
    """Share of simulated switchback tests whose interval excludes zero uplift."""
    rng = np.random.default_rng(seed)
    n = 2 * nights_each
    promo = np.array([i % 2 == 1 for i in range(n)])
    hits = 0
    for _ in range(sims):
        lam = np.where(promo, base_rate * (1 + uplift), base_rate)
        y = rng.poisson(rng.gamma(dispersion, lam / dispersion))
        daily = pd.DataFrame({"orders": y, "promo": promo, "weekday": 0, "week": np.arange(n) / 7})
        est = estimate_uplift(daily, with_trend=False, level=1 - alpha)
        hits += est.ci_low > 0
    return hits / sims
