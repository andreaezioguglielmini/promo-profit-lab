import numpy as np
import pandas as pd
import pytest

from promolab import experiments, simulate, uplift


def _daily(seed, true_uplift=0.35, days=140):
    sim = simulate.simulate(simulate.RestaurantConfig(seed=seed, true_uplift=true_uplift, days=days))
    o = sim["orders"].assign(date=lambda d: d["submitted_at"].dt.normalize(), promo=lambda d: d["discount"] > 0)
    return uplift.daily_counts(o, sim["calendar"])


def test_interval_is_calibrated_and_estimate_unbiased():
    est = [uplift.estimate_uplift(_daily(s)) for s in range(60)]
    coverage = np.mean([e.ci_low <= 0.35 <= e.ci_high for e in est])
    assert coverage >= 0.80  # nominal 90%
    assert np.mean([e.uplift for e in est]) == pytest.approx(0.35, abs=0.06)


def test_no_effect_is_not_found_too_often():
    est = [uplift.estimate_uplift(_daily(s, true_uplift=0.0)) for s in range(60)]
    false_positive = np.mean([e.ci_low > 0 for e in est])
    assert false_positive <= 0.12  # nominal 5% one-sided


def test_needs_both_arms():
    d = pd.DataFrame({"orders": [1, 2, 3], "promo": [True, True, True], "weekday": 1, "week": [0, 1, 2]})
    with pytest.raises(ValueError):
        uplift.estimate_uplift(d)


def test_power_formula_matches_simulation():
    n = experiments.nights_per_arm(3.5, 0.5, dispersion=6.0, alpha=0.10, power=0.80)
    simulated = experiments.simulate_power(3.5, 0.5, n, dispersion=6.0, alpha=0.10, sims=300)
    assert simulated == pytest.approx(0.80, abs=0.08)


def test_mde_inverts_sample_size():
    n = experiments.nights_per_arm(3.0, 0.4)
    assert experiments.minimum_detectable_uplift(3.0, n) == pytest.approx(0.4, abs=0.02)


def test_switchback_is_balanced():
    from datetime import date

    s = experiments.switchback_schedule(date(2026, 9, 1), 24, [1, 2, 3, 4, 5, 6])
    assert len(s) == 48
    assert s["promo"].sum() == 24
