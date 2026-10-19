"""Estimate how much a promo lifted nightly orders.

Model (framework section 3, level 1, at restaurant level):

    orders_t ~ quasi-Poisson,  log E[orders_t] = b0 + weekday_t + trend * week_t + beta * promo_t

exp(beta) - 1 is the uplift. Delivery data are overdispersed (some nights are
busy for reasons nobody logs), so standard errors are inflated by the Pearson
dispersion. With a few orders a night the interval is wide: the tool reports
that honestly instead of a point estimate.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

_Z = NormalDist()


@dataclass
class UpliftEstimate:
    uplift: float
    ci_low: float
    ci_high: float
    std_error_log: float
    dispersion: float
    promo_days: int
    control_days: int
    mean_orders_control: float
    mean_orders_promo: float
    trend_per_week: float | None
    method: str = "quasi-Poisson GLM with weekday effects"

    def prob_above(self, threshold: float) -> float:
        """Approximate probability that the true uplift exceeds `threshold`."""
        if math.isinf(threshold):
            return 0.0
        beta = math.log1p(self.uplift)
        return 1 - _Z.cdf((math.log1p(threshold) - beta) / self.std_error_log)

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def daily_counts(orders: pd.DataFrame, calendar: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per open night with order count and promo flag.

    `calendar` (date, promo) is the owner's log of open nights and promo nights.
    Without it, open nights are every date in range on a weekday that ever had
    orders, and a night counts as promo when most of its orders were discounted.
    """
    counts = orders.groupby("date").size().rename("orders")
    if calendar is not None:
        cal = calendar[["date", "promo"]].copy()
        cal["date"] = pd.to_datetime(cal["date"])
        df = cal.merge(counts, left_on="date", right_index=True, how="left").fillna({"orders": 0})
    else:
        promo_share = orders.groupby("date")["promo"].mean()
        dates = pd.date_range(orders["date"].min(), orders["date"].max(), freq="D")
        open_weekdays = set(orders["date"].dt.weekday)
        df = pd.DataFrame({"date": [d for d in dates if d.weekday() in open_weekdays]})
        df = df.merge(counts, left_on="date", right_index=True, how="left").fillna({"orders": 0})
        df["promo"] = df["date"].map(promo_share).fillna(0) > 0.5
    df["orders"] = df["orders"].astype(int)
    df["promo"] = df["promo"].astype(bool)
    df["weekday"] = df["date"].dt.weekday
    df["week"] = (df["date"] - df["date"].min()).dt.days / 7
    return df.sort_values("date").reset_index(drop=True)


def _design(daily: pd.DataFrame, with_trend: bool) -> tuple[np.ndarray, list[str]]:
    weekdays = sorted(daily["weekday"].unique())
    cols, names = [np.ones(len(daily))], ["intercept"]
    for wd in weekdays[1:]:
        cols.append((daily["weekday"] == wd).to_numpy(float))
        names.append(f"wd{wd}")
    if with_trend:
        cols.append(daily["week"].to_numpy(float))
        names.append("trend")
    cols.append(daily["promo"].to_numpy(float))
    names.append("promo")
    return np.column_stack(cols), names


def fit_poisson_glm(X: np.ndarray, y: np.ndarray, iters: int = 50, tol: float = 1e-9) -> tuple[np.ndarray, np.ndarray, float]:
    """Poisson regression by iteratively reweighted least squares.

    Returns coefficients, covariance scaled by the Pearson dispersion, and the dispersion.
    """
    beta = np.zeros(X.shape[1])
    beta[0] = math.log(max(y.mean(), 1e-6))
    for _ in range(iters):
        mu = np.exp(X @ beta)
        z = X @ beta + (y - mu) / mu
        W = mu
        XtW = X.T * W
        new = np.linalg.solve(XtW @ X, XtW @ z)
        if np.max(np.abs(new - beta)) < tol:
            beta = new
            break
        beta = new
    mu = np.exp(X @ beta)
    dof = max(len(y) - X.shape[1], 1)
    dispersion = max(float(np.sum((y - mu) ** 2 / mu) / dof), 1.0)
    cov = np.linalg.inv((X.T * mu) @ X) * dispersion
    return beta, cov, dispersion


def estimate_uplift(daily: pd.DataFrame, with_trend: bool = True, level: float = 0.90) -> UpliftEstimate:
    n_promo = int(daily["promo"].sum())
    n_ctrl = int((~daily["promo"]).sum())
    if n_promo < 2 or n_ctrl < 2:
        raise ValueError("need at least 2 promo nights and 2 non-promo nights to estimate an uplift")
    X, names = _design(daily, with_trend)
    beta, cov, dispersion = fit_poisson_glm(X, daily["orders"].to_numpy(float))
    i = names.index("promo")
    b, se = float(beta[i]), float(math.sqrt(cov[i, i]))
    z = _Z.inv_cdf(0.5 + level / 2)
    return UpliftEstimate(
        uplift=math.expm1(b),
        ci_low=math.expm1(b - z * se),
        ci_high=math.expm1(b + z * se),
        std_error_log=se,
        dispersion=dispersion,
        promo_days=n_promo,
        control_days=n_ctrl,
        mean_orders_control=float(daily.loc[~daily["promo"], "orders"].mean()),
        mean_orders_promo=float(daily.loc[daily["promo"], "orders"].mean()),
        trend_per_week=float(math.expm1(beta[names.index("trend")])) if with_trend else None,
    )
