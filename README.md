# Olist Commercial Audit: Revenue Concentration & Customer Retention Analysis

An analytical evaluation and interactive Streamlit dashboard examining the concentration of realized sales revenue across product categories, Brazilian states, and customer repeat purchase dynamics using the Olist e-commerce dataset (~100k records).

---

## 📌 Executive Summary & Core Business Question

> **Primary Objective:** Which product categories and customer states drive the highest sales revenue, and do those high-value customers ever return to buy again?

* **Revenue Drivers:** Gross fulfilled marketplace revenue is heavily concentrated in everyday consumer categories (`health_beauty`, `watches_gifts`, and `bed_bath_table`) and clustered geographically in Southeast Brazil (`SP`, `RJ`, and `MG`).
* **The Retention Problem:** Despite heavy order volume in primary urban centers, customer loyalty does not scale with market size. Repeat purchase rates remain compressed between **1.8% and 3.3%** across all states.
* **Customer Profile:** Average lifetime order frequency per unique buyer is **1.03 orders**. High spend is primarily driven by single large transactions (high-ticket items or bulk unit buys) rather than cumulative repeat business over time.

---

## 🗂️ Data Architecture & Relational Model

The project operates exclusively on six normalized relational tables from the Kaggle Olist dataset:

| Entity | Primary Key / Grain | Key Columns Utilized |
| :--- | :--- | :--- |
| `orders` | `order_id` | `order_id`, `customer_id`, `order_status`, `order_purchase_timestamp` |
| `order_items` | `(order_id, order_item_id)` | `order_id`, `order_item_id`, `product_id`, `price`, `freight_value` |
| `order_payments` | `(order_id, payment_sequential)` | `order_id`, `payment_value`, `payment_type`, `payment_installments` |
| `customers` | `customer_id` | `customer_id`, `customer_unique_id`, `customer_state`, `customer_city` |
| `products` | `product_id` | `product_id`, `product_category_name` |
| `product_category_name_translation` | `product_category_name` | `product_category_name`, `product_category_name_english` |

---

## ⚙️ Business Assumptions

1. **Fulfilled Deliveries Only (`order_status == 'delivered'`):**  
   To evaluate realized commercial sales rather than unfulfilled or in-transit intent, only orders with `order_status == 'delivered'` are retained. Canceled, unavailable, shipped, or processing orders are filtered out of all revenue and retention metrics.
2. **Revenue Definitions by Granularity:**  
   * **Product Category Revenue:** Measured as `SUM(price)` (or `price + freight_value`) directly from `order_items`. Payment records are not joined here to avoid Cartesian fan-out errors.
   * **State & Customer Spend:** Measured as total fulfilled monetary inflow (`payment_value`) aggregated at the order level first.
3. **Customer Identification (`customer_id` vs. `customer_unique_id`):**  
   In Olist, `customer_id` is an ephemeral checkout session ID generated for every transaction. All loyalty, repeat purchase, and lifetime metrics must aggregate strictly on `customer_unique_id`, which represents the actual recurring buyer profile.
4. **Repeat Customer Threshold:**  
   A buyer is categorized as a repeat customer if `COUNT(DISTINCT order_id) > 1` across delivered orders.
5. **Customer State Assignment:**  
   If a buyer recorded orders across multiple states, their primary location is assigned via statistical mode (`mode()[0]`), with the first recorded state used as a fallback.

   ---

## 🧹 Data Cleaning, Audits & Common Pitfalls

### 1. The Multi-Quantity Duplicate Trap
* **Symptom:** Running df.duplicated() on a reduced subset of columns (order_id, product_id, price) flags 10,000+ rows as duplicates.
* **Audit:** In Olist, purchasing multiple units of the same item creates identical rows, differentiated only by order_item_id (1, 2, 3...). Dropping duplicates based on product and price deletes valid fulfilled sales volume.
* **Resolution:** Preserved order_item_id in the pipeline to maintain row integrity and ensure every purchased unit contributes to category and platform totals.

### 2. Preventing Join Fan-Out on Payments
* **Symptom:** Joining order_payments directly to order_items produces Cartesian row multiplication when an order contains both multiple items and split payment methods (e.g., credit card combined with a voucher).
* **Resolution:** Aggregated order_payments to the order_id level (SUM payment_value) before joining with orders and customer tables.

### 3. Mitigating View Slicing Warnings
* **Symptom:** Deriving custom calculated fields like Revenue = price + freight_value on filtered slices triggered Pandas SettingWithCopyWarning.
* **Resolution:** Explicitly instantiated copies via .copy() on dataframe slices before feature engineering.

---

## 🔄 Step-by-Step Analytical Workflow

1. Ingestion & Quality Filtering:
   - Load the 6 raw CSV files.
   - Filter strictly for fulfilled deliveries: orders['order_status'] == 'delivered'.

2. Category Performance Pipeline:
   - Join order_items with products and product_category_name_translation.
   - Group by product_category_name_english.
   - Calculate total sales (SUM price), order volume (COUNT order_item_id), and average price (MEAN price).

3. Customer & State Modeling Pipeline:
   - Aggregate order_payments by order_id (SUM payment_value).
   - Join aggregated payments with delivered orders and customers.
   - Group by customer_unique_id to profile individual buyer behavior:
     - total_orders = nunique(order_id)
     - total_spent = sum(payment_value)
     - is_repeat = total_orders > 1
     - primary_state = mode(customer_state)

4. Geographic Retention Pipeline:
   - Group customer profiles by primary_state.
   - Calculate total_revenue = sum(total_spent).
   - Calculate total_buyers = count(customer_unique_id).
   - Calculate repeat_buyers = sum(is_repeat).
   - Calculate repeat_pct = (repeat_buyers / total_buyers) * 100.

5. Presentation Layer:
   - Build an interactive Streamlit UI with Plotly charts and key KPI callouts.

   ---

## 📊 Key Findings

* SP (São Paulo): Gross Revenue = R$ 5.77M | Unique Buyers = 39,141 | Repeat Rate = 3.11%
* RJ (Rio de Janeiro): Gross Revenue = R$ 2.06M | Unique Buyers = 11,915 | Repeat Rate = 3.29%
* MG (Minas Gerais): Gross Revenue = R$ 1.82M | Unique Buyers = 11,000 | Repeat Rate = 2.96%
* Platform Average: Repeat Rate = ~3.00% | Avg Orders / Buyer = 1.03

Core Analytical Insights:
- Volume Does Not Drive Retention: High-population urban states generate massive volume but fail to produce higher loyalty. Repeat purchase rates remain flat across both high-volume hubs and smaller frontier states.
- Acquisition Dominance: Olist operates primarily as a one-time transaction engine rather than a compounding retention engine.
- High-Spend Behavior: Top-spending customer accounts accumulate high spend through single high-ticket or multi-unit orders rather than multiple checkout cycles over time.

---

## 🛠️ Tech Stack & Dependencies

- Language: Python 3.10+
- Data Wrangling: Pandas, NumPy
- Data Visualization: Plotly Express, Plotly Graph Objects
- Application Framework: Streamlit

---

## 🚀 Setup & Execution

1. Clone the repository:
git clone https://github.com/leodera/olist-revenue-retention.git
cd olist-revenue-retention

2. Create and activate a virtual environment:
# On Windows:
python -m venv venv
venv\Scripts\activate

# On Linux or macOS:
python3 -m venv venv
source venv/bin/activate

3. Install required packages:
pip install -r requirements.txt

4. Project directory structure:
olist-revenue-retention/
├── data/
│   ├── olist_orders_dataset.csv
│   ├── olist_order_items_dataset.csv
│   ├── olist_order_payments_dataset.csv
│   ├── olist_products_dataset.csv
│   ├── product_category_name_translation.csv
│   └── olist_customers_dataset.csv
├── app.py
├── requirements.txt
└── README.md

5. Run the Streamlit application:
streamlit run app.py