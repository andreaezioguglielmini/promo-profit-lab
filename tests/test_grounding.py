from promolab import grounding


def test_parses_italian_and_english_numbers():
    assert grounding.parse_number("1.234,56") == (1234.56, 2)
    assert grounding.parse_number("3,4") == (3.4, 1)
    assert grounding.parse_number("12.5") == (12.5, 1)
    assert grounding.parse_number("1.500") == (1500.0, 0)


def test_accepts_rounding_and_percentages():
    tools = [{"breakeven_uplift": 0.5966, "margin": 9.876, "nights": 64}]
    r = grounding.check("Servono il 60% di ordini in più, margine €9,88, cioè 9,9, per 64 sere.", tools)
    assert r.ok, r.ungrounded


def test_flags_invented_figures():
    r = grounding.check("Hai perso €412,50 e gli ordini sono saliti del 37%.", [{"x": 0.36, "y": 400}])
    assert r.ungrounded == ["412,50", "37%"]


def test_ignores_dates_small_counts_and_list_markers():
    r = grounding.check("1. Dal 2026-07-21 per 3 settimane\n2. Nel 2026 a sere alterne", [])
    assert r.ok and r.numbers == []
