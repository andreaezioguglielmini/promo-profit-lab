import math

import pandas as pd
import pytest

from promolab import margins


def test_framework_worked_example():
    # docs/framework.md section 5: EUR 10 pizza, 30% commission, EUR 2.50 food, EUR 0.50 packaging
    m0 = margins.unit_margin(10, 0.30, 2.5, 0.5)
    assert m0 == pytest.approx(4.00)
    assert margins.promo_margin(10, 0.20, 0.30, 2.5, 0.5) == pytest.approx(2.60)
    assert margins.breakeven_uplift(m0, 2.60) == pytest.approx(0.538, abs=1e-3)
    assert margins.breakeven_uplift(m0, margins.promo_margin(10, 0.30, 0.30, 2.5, 0.5)) == pytest.approx(1.105, abs=1e-3)


def test_partial_incrementality_raises_the_bar():
    assert margins.breakeven_uplift(4.0, 2.6, incrementality=0.6) == pytest.approx(0.897, abs=1e-3)


def test_negative_promo_margin_never_breaks_even():
    m1 = margins.promo_margin(6, 0.5, 0.3, 2.5, 0.5)
    assert m1 < 0
    assert math.isinf(margins.breakeven_uplift(1.2, m1))


def test_commission_on_full_price_costs_more():
    a = margins.promo_margin(10, 0.2, 0.3, 2.5, 0.5, commission_base="discounted")
    b = margins.promo_margin(10, 0.2, 0.3, 2.5, 0.5, commission_base="full")
    assert b == pytest.approx(a - 0.2 * 10 * 0.3)


def test_max_discount_respects_floor():
    d = margins.max_discount_for_floor(10, 0.3, 2.5, 0.5, margin_floor=1.5)
    assert margins.promo_margin(10, d, 0.3, 2.5, 0.5) == pytest.approx(1.5)


def test_two_for_one_doubles_cost():
    assert margins.two_for_one_margin(10, 0.3, 2.5, 0.5) == pytest.approx(1.0)


def test_decomposition_adds_up():
    parts = margins.decompose_delta_profit(q0=100, q1=130, m0=4.0, m1=2.6)
    assert parts["net"] == pytest.approx(margins.delta_profit(100, 130, 4.0, 2.6))


def test_breakeven_table_shape():
    menu = pd.DataFrame([{"name": "a", "price": 10, "food_cost": 3}, {"name": "b", "price": 5, "food_cost": 1}])
    t = margins.breakeven_table(menu, [0.1, 0.2], commission=0.25)
    assert len(t) == 4
    assert (t.groupby("name")["breakeven_uplift"].apply(lambda s: s.is_monotonic_increasing)).all()
