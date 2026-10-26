import streamlit as st
import pandas as pd
import requests
import plotly.express as px

# ---------------------------------------------------------
# Page Setup
# ---------------------------------------------------------
st.set_page_config(
    page_title="Olist Commercial and Retention Audit",
    layout="wide"
)

# ---------------------------------------------------------
# Data Processing Pipeline (Parquet Loader + Business Model)
# ---------------------------------------------------------
@st.cache_data(ttl="6h")
def load_parquet_data():
    owner = "leodera"
    repo = "file_explorer"
    path = "olist"
    
    # Safely retrieve token from st.secrets
    token = st.secrets["GITHUB_TOKEN"]
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    contents = response.json()
    
    storage = {"Authorization": f"Bearer {token}"}
    dfs = {}
    
    for file in contents:
        if file.get("type") == "file" and file["name"].endswith(".parquet"):
            key_name = file["name"].replace(".parquet", "")
            download_url = file["download_url"]
            dfs[key_name] = pd.read_parquet(download_url, storage_options=storage)
            
    # Unpack individual tables
    customers = dfs.get("customers")
    orders = dfs.get("orders")
    items = dfs.get("order_items")
    payments = dfs.get("payments")
    products = dfs.get("products")
    categories = dfs.get("product_category")
    
    # 1. Fulfilled orders only
    delivered_orders = orders[orders["order_status"] == "delivered"].copy()
    
    # 2. Product items pipeline (preserves order_item_id)
    delivered_items = items.merge(delivered_orders[["order_id"]], on="order_id", how="inner")
    df_items = (
        delivered_items.merge(products, on="product_id", how="inner")
        .merge(categories, on="product_category_name", how="inner")
    )
    
    # 3. Pre-aggregate payments by order_id to prevent join fan-out
    order_payments = payments.groupby("order_id")["payment_value"].sum().reset_index()
    
    # 4. Join at order grain
    df_orders = (
        delivered_orders.merge(customers, on="customer_id", how="inner")
        .merge(order_payments, on="order_id", how="left")
    )
    
    # 5. Customer grain profile (using customer_unique_id)
    customer_profile = df_orders.groupby("customer_unique_id").agg(
        total_orders=("order_id", "nunique"),
        total_spent=("payment_value", "sum"),
        customer_state=("customer_state", lambda s: s.mode()[0] if not s.mode().empty else s.iloc[0])
    ).reset_index()
    
    customer_profile["is_repeat"] = customer_profile["total_orders"] > 1
    
    # 6. State grain aggregation
    state_summary = customer_profile.groupby("customer_state").agg(
        total_revenue=("total_spent", "sum"),
        total_buyers=("customer_unique_id", "nunique"),
        repeat_buyers=("is_repeat", "sum")
    ).reset_index()
    
    state_summary["repeat_pct"] = (state_summary["repeat_buyers"] / state_summary["total_buyers"]) * 100
    state_summary = state_summary.sort_values(by="total_revenue", ascending=False)
    
    return df_items, customer_profile, state_summary

with st.spinner("Processing delivered transactions from Parquet storage..."):
    df_items, customer_profile, state_summary = load_parquet_data()

# ---------------------------------------------------------
# Sidebar Navigation and Filtering
# ---------------------------------------------------------
st.sidebar.title("Filter Panel")
st.sidebar.write("Refine geographic analysis across Brazilian states:")

all_states = sorted(state_summary["customer_state"].unique().tolist())
selected_states = st.sidebar.multiselect(
    "Select Customer States",
    options=all_states,
    default=[]
)

filtered_states = state_summary.copy()
filtered_customers = customer_profile.copy()

if selected_states:
    filtered_states = filtered_states[filtered_states["customer_state"].isin(selected_states)]
    filtered_customers = filtered_customers[filtered_customers["customer_state"].isin(selected_states)]

# ---------------------------------------------------------
# Top Executive Metrics
# ---------------------------------------------------------
st.title("Olist Revenue Drivers and Customer Retention Audit")
st.caption("Commercial analysis strictly on realized transactions (order_status == 'delivered')")

k1, k2, k3, k4 = st.columns(4)

total_rev = filtered_states["total_revenue"].sum()
unique_buyers = filtered_customers["customer_unique_id"].nunique()
repeat_buyers_count = filtered_customers["is_repeat"].sum()
repeat_rate = (repeat_buyers_count / unique_buyers * 100) if unique_buyers > 0 else 0.0
avg_orders = filtered_customers["total_orders"].mean() if unique_buyers > 0 else 0.0
formatted_rev = f"R$ {total_rev / 1e6:.2f}M" if total_rev >= 1e6 else f"R$ {total_rev / 1e3:.1f}k"


k1.metric("Delivered Revenue", formatted_rev)
k2.metric("Unique Buyers", f"{unique_buyers:,}")
k3.metric("Platform Repeat Rate", f"{repeat_rate:.2f}%")
k4.metric("Avg Orders / Buyer", f"{avg_orders:.2f}")

st.divider()

# ---------------------------------------------------------
# Tabbed Visualizations
# ---------------------------------------------------------
tab_cat, tab_geo, tab_ret = st.tabs([
    "Product Categories",
    "Geographic Concentration",
    "Customer Retention"
])

# --- Tab 1: Product Categories ---
with tab_cat:
    st.subheader("Top Revenue-Generating Product Categories")
    top_n = st.slider("Select Number of Top Categories", min_value=5, max_value=25, value=10)

    cat_df = df_items.groupby("product_category_name_english").agg(
        gross_sales=("price", "sum"),
        units_sold=("order_item_id", "count"),
        avg_item_price=("price", "mean")
    ).reset_index().sort_values(by="gross_sales", ascending=False).head(top_n)

    fig_cat = px.bar(
        cat_df,
        x="gross_sales",
        y="product_category_name_english",
        orientation="h",
        text=cat_df["gross_sales"].apply(lambda v: f"R$ {v/1e6:.2f}M" if v >= 1e6 else f"R$ {v/1e3:.1f}k"),
        color="gross_sales",
        color_continuous_scale="Blues",
        labels={"gross_sales": "Gross Sales (R$)", "product_category_name_english": "Category"},
        title=f"Top {top_n} Product Categories by Sales Value (Delivered)"
    )
    fig_cat.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False, height=500)
    fig_cat.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_cat, use_container_width=True)

    with st.expander("Inspect Category Data Table"):
        st.dataframe(cat_df.style.format({
            "gross_sales": "R$ {:,.2f}",
            "units_sold": "{:,}",
            "avg_item_price": "R$ {:,.2f}"
        }), use_container_width=True)

# --- Tab 2: Geographic Concentration ---
with tab_geo:
    st.subheader("State Revenue vs. Repeat Retention")
    c1, c2 = st.columns(2)

    with c1:
        top_10_states = filtered_states.head(10)
        fig_st_rev = px.bar(
            top_10_states,
            x="total_revenue",
            y="customer_state",
            orientation="h",
            color="total_revenue",
            color_continuous_scale="Viridis",
            labels={"total_revenue": "Fulfilled Revenue (R$)", "customer_state": "State"},
            title="Top 10 States by Fulfilled Payment Value"
        )
        fig_st_rev.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False, height=450)
        st.plotly_chart(fig_st_rev, use_container_width=True)

    with c2:
        fig_scatter = px.scatter(
            filtered_states,
            x="total_revenue",
            y="repeat_pct",
            size="total_buyers",
            text="customer_state",
            labels={"total_revenue": "Total Revenue (R$)", "repeat_pct": "Repeat Rate (%)"},
            title="State Revenue vs. Repeat Purchase Rate %"
        )
        fig_scatter.update_traces(textposition="top center")
        fig_scatter.update_layout(height=450)
        st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown(
        "> **Key Finding:** While São Paulo (SP), Rio de Janeiro (RJ), and Minas Gerais (MG) account for the vast majority of revenue, their repeat rates hover between **2.9% and 3.3%**. Volume does not drive customer loyalty."
    )

# --- Tab 3: Customer Retention and Profiling ---
with tab_ret:
    st.subheader("Customer Frequency and High-Spender Analysis")
    col_dist, col_high = st.columns([1, 2])

    with col_dist:
        freq_df = filtered_customers["total_orders"].value_counts().reset_index()
        freq_df.columns = ["Lifetime Orders", "Total Buyers"]
        freq_df["Share"] = (freq_df["Total Buyers"] / freq_df["Total Buyers"].sum()) * 100

        st.write("##### Order Frequency Breakdown")
        st.dataframe(freq_df.style.format({
            "Total Buyers": "{:,}",
            "Share": "{:.2f}%"
        }), use_container_width=True)

    with col_high:
        top_spenders = filtered_customers.sort_values(by="total_spent", ascending=False).head(10).copy()
        top_spenders["clean_label"] = [f"Customer #{i+1} ({row.customer_state})" for i, row in enumerate(top_spenders.itertuples())]

        fig_spenders = px.bar(
            top_spenders,
            x="total_spent",
            y="clean_label",
            orientation="h",
            color="total_orders",
            labels={"total_spent": "Total Lifetime Spend (R$)", "clean_label": "Customer", "total_orders": "Orders Placed"},
            title="Top 10 Highest Spending Accounts (Color = Lifetime Orders)"
        )
        fig_spenders.update_layout(yaxis={"categoryorder": "total ascending"}, height=420)
        st.plotly_chart(fig_spenders, use_container_width=True)

    st.info(
        "Commercial Finding: High-spending buyers are primarily one-time buyers who placed large single orders or multi-unit purchases rather than accumulating value over repeated visits."
    )