"""Parse raw Deliveroo Partner Hub exports (Italian locale) into tidy tables.

Each export type is recognised from its header row, so files can keep whatever
name the owner saved them under. Supported:

- orders     ("Numero d'ordine", "Subtotale", "Commissione Deliveroo", ...)
- products   ("Nome articolo", "Quantità", "Prezzo", ...) one file per period
- ads        ("Total Ad Spend", "Total Orders (clicks)", ...)
- customers  ("Ordini effettuati da nuovi clienti", ...)
- kpis       ("Vendite lorde", "Ordini consegnati", ...)
- costs      ("Nome articolo", "Food cost", ...) filled in by the owner
- calendar   ("Data", "Promo attiva", "Sconto") the owner's log of open and promo nights
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

SIGNATURES: dict[str, set[str]] = {
    "orders": {"Numero d'ordine", "Subtotale", "Data di invio"},
    "costs": {"Nome articolo", "Food cost"},
    "products": {"Nome articolo", "Quantità", "Prezzo"},
    "ads": {"Total Ad Spend", "Total Orders (clicks)"},
    "customers": {"Ordini effettuati da nuovi clienti"},
    "kpis": {"Vendite lorde", "Ordini consegnati"},
    "calendar": {"Data", "Promo attiva"},
}


def detect_kind(columns: list[str]) -> str | None:
    cols = {c.strip() for c in columns}
    for kind, required in SIGNATURES.items():  # order matters: costs before products
        if required <= cols:
            return kind
    return None


def read_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    return df


def parse_orders(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "order_id": df["Numero d'ordine"],
            "status": df.get("Stato dell'ordine", "Completato"),
            "submitted_at": pd.to_datetime(df["Data di invio"] + " " + df["Orario di invio"]),
            "subtotal": pd.to_numeric(df["Subtotale"]),
            "discount": pd.to_numeric(df["Sconto offerte"]) if "Sconto offerte" in df else 0.0,
            "commission": pd.to_numeric(df.get("Commissione Deliveroo", 0.0)),
            "vat_on_commission": pd.to_numeric(df.get("IVA su commissione Deliveroo", 0.0)),
        }
    )
    if "Data di consegna" in df and "Orario di consegna" in df:
        out["delivered_at"] = pd.to_datetime(df["Data di consegna"] + " " + df["Orario di consegna"])
    out = out[out["status"].str.lower().str.startswith("complet")].copy()
    out["paid"] = out["subtotal"] - out["discount"]
    out["date"] = out["submitted_at"].dt.normalize()
    out["promo"] = out["discount"] > 0
    return out.reset_index(drop=True)


_PERIOD_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})")


def parse_products(df: pd.DataFrame, source: str = "") -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "category": df["Categoria"].fillna("Altro").str.strip(),
            "name": df["Nome articolo"].str.replace(r"\s+", " ", regex=True).str.strip(),
            "qty": pd.to_numeric(df["Quantità"]),
            "price": pd.to_numeric(df["Prezzo"]),
            "revenue": pd.to_numeric(df["Subtotale"]),
        }
    )
    m = _PERIOD_RE.search(source)
    out["period_start"] = pd.Timestamp(m.group(1)) if m else pd.NaT
    out["period_end"] = pd.Timestamp(m.group(2)) if m else pd.NaT
    out["source"] = Path(source).name
    # Zero-price rows are modifiers (sauces, choices), not dishes.
    return out[out["price"] > 0].reset_index(drop=True)


def parse_ads(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(df["Date"]),
            "clicks": pd.to_numeric(df.get("Total Clicks", 0)).fillna(0),
            "spend": pd.to_numeric(df["Total Ad Spend"]).fillna(0),
            "sales": pd.to_numeric(df.get("Total Sales (clicks)", 0)).fillna(0),
            "orders": pd.to_numeric(df["Total Orders (clicks)"]).fillna(0),
        }
    )


def parse_costs(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": df["Nome articolo"].str.strip(),
            "category": df.get("Categoria", "Altro"),
            "price": pd.to_numeric(df["Prezzo"]),
            "food_cost": pd.to_numeric(df["Food cost"]),
            "packaging": pd.to_numeric(df.get("Packaging", 0.0)),
        }
    )


def parse_calendar(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(df["Data"]),
            "promo": df["Promo attiva"].astype(str).str.lower().isin(["si", "sì", "yes", "true", "1"]),
            "discount": pd.to_numeric(df.get("Sconto", 0.0)).fillna(0.0),
        }
    )


@dataclass
class Dataset:
    """Everything parsed from one folder of exports."""

    orders: pd.DataFrame | None = None
    products: pd.DataFrame | None = None
    ads: pd.DataFrame | None = None
    costs: pd.DataFrame | None = None
    calendar: pd.DataFrame | None = None
    customers: pd.DataFrame | None = None
    kpis: pd.DataFrame | None = None
    files: dict[str, str] = field(default_factory=dict)  # file name -> detected kind
    skipped: list[str] = field(default_factory=list)


def load_folder(folder: str | Path) -> Dataset:
    ds = Dataset()
    products = []
    for path in sorted(Path(folder).glob("*.csv")):
        df = read_csv(path)
        kind = detect_kind(list(df.columns))
        if kind is None:
            ds.skipped.append(path.name)
            continue
        ds.files[path.name] = kind
        if kind == "orders":
            ds.orders = _concat(ds.orders, parse_orders(df))
        elif kind == "products":
            products.append(parse_products(df, path.name))
        elif kind == "ads":
            ds.ads = _concat(ds.ads, parse_ads(df))
        elif kind == "costs":
            ds.costs = parse_costs(df)
        elif kind == "calendar":
            ds.calendar = parse_calendar(df)
        elif kind == "customers":
            ds.customers = df
        elif kind == "kpis":
            ds.kpis = df
    if products:
        ds.products = pd.concat(products, ignore_index=True)
    return ds


def _concat(a: pd.DataFrame | None, b: pd.DataFrame) -> pd.DataFrame:
    return b if a is None else pd.concat([a, b], ignore_index=True)
