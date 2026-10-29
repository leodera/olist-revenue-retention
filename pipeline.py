"""
Data pipeline for the Olist revenue and retention audit.

Pure pandas (no Streamlit), so it can be tested on its own.

ONE REVENUE DEFINITION FOR THE WHOLE PROJECT
    Revenue = sum of item `price` on delivered orders (freight excluded).
    Category, state and customer totals are all built from the same item rows,
    so they always add up to the same number.

Why not `payment_value`?
    payment_value is the cash collected. It includes freight and any installment
    interest on top of item price, so it is higher than item price (about R$ 15M
    instead of about R$ 13M for this dataset). The gap is shown in the dashboard's
    reconciliation table instead of being mixed into the headline number.
"""
import pandas as pd


def build_tables(customers, orders, items, payments, products, categories):
    """Return (df_items, customer_profile, state_summary, recon)."""
    # 1. Fulfilled orders only
    delivered_orders = orders.loc[orders["order_status"] == "delivered", ["order_id", "customer_id"]].copy()

    # 2. Delivered item rows with their English category.
    #    Left joins keep every sold unit; items with no category become "Uncategorized"
    #    (an inner join would silently drop them and shrink the category total).
    delivered_items = items.merge(delivered_orders[["order_id"]], on="order_id", how="inner")
    df_items = (
        delivered_items.merge(products[["product_id", "product_category_name"]], on="product_id", how="left")
        .merge(
            categories[["product_category_name", "product_category_name_english"]],
            on="product_category_name",
            how="left",
        )
    )
    df_items["product_category_name_english"] = df_items["product_category_name_english"].fillna("Uncategorized")

    # Safety check: a lookup table with duplicate keys would repeat item rows and inflate revenue.
    if len(df_items) != len(delivered_items):
        raise ValueError(
            f"Joining products/categories changed the number of item rows "
            f"({len(delivered_items)} -> {len(df_items)}). Check for duplicate keys in those tables."
        )

    # 3. One revenue number per order = sum of its item prices.
    #    (No payments join here, so there is nothing to fan out.)
    order_revenue = df_items.groupby("order_id")["price"].sum().rename("order_revenue").reset_index()
    df_orders = (
        delivered_orders.merge(
            customers[["customer_id", "customer_unique_id", "customer_state"]], on="customer_id", how="inner"
        )
        .merge(order_revenue, on="order_id", how="left")
    )
    df_orders["order_revenue"] = df_orders["order_revenue"].fillna(0.0)

    # 4. Customer grain profile (customer_unique_id = the real person)
    customer_profile = (
        df_orders.groupby("customer_unique_id")
        .agg(
            total_orders=("order_id", "nunique"),
            total_spent=("order_revenue", "sum"),
            customer_state=("customer_state", lambda s: s.mode()[0] if not s.mode().empty else s.iloc[0]),
        )
        .reset_index()
    )
    customer_profile["is_repeat"] = customer_profile["total_orders"] > 1

    # 5. State grain aggregation
    state_summary = (
        customer_profile.groupby("customer_state")
        .agg(
            total_revenue=("total_spent", "sum"),
            total_buyers=("customer_unique_id", "nunique"),
            repeat_buyers=("is_repeat", "sum"),
        )
        .reset_index()
    )
    state_summary["repeat_pct"] = state_summary["repeat_buyers"] / state_summary["total_buyers"] * 100
    state_summary = state_summary.sort_values(by="total_revenue", ascending=False)

    # 6. Reconciliation numbers (platform-wide, delivered orders)
    delivered_payments = payments.merge(delivered_orders[["order_id"]], on="order_id", how="inner")
    recon = {
        "delivered_orders": int(delivered_orders["order_id"].nunique()),
        "item_price": float(df_items["price"].sum()),
        "freight": float(df_items["freight_value"].sum()),
        "payment_value": float(delivered_payments["payment_value"].sum()),
        "state_total": float(state_summary["total_revenue"].sum()),
    }
    return df_items, customer_profile, state_summary, recon
