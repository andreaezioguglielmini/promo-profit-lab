from promolab import ingest, simulate


def test_exports_round_trip(tmp_path):
    sim = simulate.simulate(simulate.RestaurantConfig(days=42, seed=1))
    simulate.write_exports(sim, tmp_path)
    ds = ingest.load_folder(tmp_path)
    kinds = set(ds.files.values())
    assert {"orders", "products", "ads", "costs", "calendar"} <= kinds
    assert len(ds.orders) == len(sim["orders"])
    assert ds.products["qty"].sum() == len(sim["lines"])
    assert ds.calendar["promo"].sum() == sim["truth"].promo_days


def test_real_export_headers_are_recognised():
    # Header rows copied from the Deliveroo Partner Hub (Italian locale); no data rows.
    orders = [
        "Nome del ristorante",
        "Numero d'ordine",
        "Stato dell'ordine",
        "Data di invio",
        "Orario di invio",
        "Subtotale",
        "Commissione Deliveroo",
    ]
    products = ["Nome del ristorante", "Categoria", "Nome articolo", "Quantità", "Prezzo", "Subtotale"]
    ads = ["Date", "Total Clicks", "Total Ad Spend", "Total Sales (clicks)", "Total Orders (clicks)"]
    assert ingest.detect_kind(orders) == "orders"
    assert ingest.detect_kind(products) == "products"
    assert ingest.detect_kind(ads) == "ads"
    assert ingest.detect_kind(["foo"]) is None


def test_ground_truth_matches_definition():
    t = simulate.simulate(simulate.RestaurantConfig(true_uplift=0.9, promo_discount=0.1, seed=3))["truth"]
    assert t.promo_is_profitable == (t.true_uplift > t.breakeven_uplift)
