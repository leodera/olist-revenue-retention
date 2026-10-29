"""
Turns the six raw Olist tables into a few small summary files that the Dash app reads.

WHY THIS STEP EXISTS
    The raw tables are large (and the earlier version downloaded them from a private
    GitHub repo every time the app started). Doing the heavy work ONCE, here, makes the
    app start fast, needs no secret token on the web server, and keeps customer-level
    data out of the public repo.

RUN IT ON YOUR COMPUTER (not on Render), then commit the data_summary/ folder
    python prepare_data.py --source local --data-dir data
    python prepare_data.py --source github          (needs the GITHUB_TOKEN environment variable)

    --source local   reads the six Kaggle CSV files (plain or .zip) from the data/ folder
    --source github  reads the parquet files from leodera/file_explorer (the old route)

OUTPUT (in data_summary/)
    category_summary.csv   one row per category
    state_summary.csv      one row per state (revenue, buyers, repeat buyers, orders)
    freq_by_state.csv      how many buyers placed 1, 2, 3... orders, per state
    top_spenders.csv       the 10 highest-spending buyers per state (no customer ids)
    recon.json             item price vs. freight vs. payments collected
"""
import argparse
import json
import os
from pathlib import Path

import pandas as pd

from pipeline import build_tables

LOCAL_FILES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "products": "olist_products_dataset.csv",
    "product_category": "product_category_name_translation.csv",
}


def load_local(data_dir: str) -> dict:
    tables = {}
    for key, filename in LOCAL_FILES.items():
        path = Path(data_dir) / filename
        zipped = Path(data_dir) / (filename + ".zip")  # Kaggle downloads are often zipped; pandas reads them directly
        if path.exists():
            tables[key] = pd.read_csv(path)
        elif zipped.exists():
            tables[key] = pd.read_csv(zipped)
        else:
            raise SystemExit(f"Missing {filename} (or {filename}.zip) in the '{data_dir}' folder.")
    return tables


def load_github() -> dict:
    """The old route: parquet files in a private GitHub repo (kept so nothing is lost)."""
    import requests  # only needed for this route

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Set the GITHUB_TOKEN environment variable first.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    api_url = "https://api.github.com/repos/leodera/file_explorer/contents/olist"
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    storage = {"Authorization": f"Bearer {token}"}
    tables = {}
    for file in response.json():
        if file.get("type") == "file" and file["name"].endswith(".parquet"):
            tables[file["name"].replace(".parquet", "")] = pd.read_parquet(file["download_url"], storage_options=storage)
    missing = [k for k in LOCAL_FILES if k not in tables]
    if missing:
        raise SystemExit(f"Missing tables from GitHub: {missing}")
    return tables


def write_summaries(df_items, customer_profile, state_summary, recon, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    category = (
        df_items.groupby("product_category_name_english")
        .agg(gross_sales=("price", "sum"), units_sold=("order_item_id", "count"), avg_item_price=("price", "mean"))
        .reset_index()
        .rename(columns={"product_category_name_english": "category"})
        .sort_values("gross_sales", ascending=False)
    )

    orders_by_state = customer_profile.groupby("customer_state")["total_orders"].sum().rename("total_orders").reset_index()
    state = state_summary.drop(columns=["repeat_pct"]).merge(orders_by_state, on="customer_state")
    state["repeat_buyers"] = state["repeat_buyers"].astype(int)
    state = state.sort_values("total_revenue", ascending=False)

    freq = (
        customer_profile.groupby(["customer_state", "total_orders"]).size().reset_index(name="buyers")
        .rename(columns={"total_orders": "lifetime_orders"})
    )

    top = (
        customer_profile.sort_values("total_spent", ascending=False)
        .groupby("customer_state").head(10)[["customer_state", "total_spent", "total_orders"]]
    )

    category.round(2).to_csv(out_dir / "category_summary.csv", index=False)
    state.round(2).to_csv(out_dir / "state_summary.csv", index=False)
    freq.to_csv(out_dir / "freq_by_state.csv", index=False)
    top.round(2).to_csv(out_dir / "top_spenders.csv", index=False)
    (out_dir / "recon.json").write_text(json.dumps({k: round(v, 2) for k, v in recon.items()}, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["local", "github"], default="local")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="data_summary")
    args = ap.parse_args()

    t = load_local(args.data_dir) if args.source == "local" else load_github()
    df_items, customer_profile, state_summary, recon = build_tables(
        t["customers"], t["orders"], t["order_items"], t["payments"], t["products"], t["product_category"]
    )
    write_summaries(df_items, customer_profile, state_summary, recon, Path(args.out_dir))

    print(f"Wrote summaries to {args.out_dir}/")
    print(f"  delivered orders        : {recon['delivered_orders']:,}")
    print(f"  revenue (item price)    : R$ {recon['item_price']:,.2f}")
    print(f"  freight                 : R$ {recon['freight']:,.2f}")
    print(f"  payments collected      : R$ {recon['payment_value']:,.2f}")
    print(f"  state total == item total: {abs(recon['state_total'] - recon['item_price']) < 0.5}")
    print(f"  unique buyers           : {len(customer_profile):,}")
    print(f"  repeat rate             : {customer_profile['is_repeat'].mean() * 100:.2f}%")


if __name__ == "__main__":
    main()
