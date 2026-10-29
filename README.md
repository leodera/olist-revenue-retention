# Olist Revenue Drivers & Customer Retention Audit

An interactive Dash dashboard on the Olist Brazilian e-commerce dataset (about 100k orders).

## Business question
> Which product categories and customer states drive the most revenue, and do those customers ever come back to buy again?

## Key findings
- **Revenue is concentrated in the Southeast.** SP, RJ and MG lead on delivered revenue, and the dashboard shows each state's share.
- **Loyalty is low everywhere.** Repeat purchase rates stay between about 1.8% and 3.3% across states, with a platform average near 3% and about 1.03 orders per buyer.
- **Market size does not predict loyalty.** The Geographic tab computes the rank correlation between state revenue and repeat rate, so this statement is tested on the data and updates with the state filter.
- **Olist behaves like a one-time transaction engine.** The Retention tab compares how many of the top spenders ordered only once with the share of one-time buyers overall.

All figures on the dashboard are calculated from the data, not typed in.

## Method
- **Orders:** delivered orders only (`order_status == 'delivered'`).
- **Revenue:** sum of item `price` (freight excluded), used for the category, state and customer views, so they all add up to the same total.
- **Reconciliation:** the dashboard has a panel that compares item price with freight and with payments collected (`payment_value`). Payments are higher because they also include freight and any installment interest.
- **Customers:** loyalty uses `customer_unique_id`, because `customer_id` is a new ID for every order.
- **Repeat buyer:** a customer with more than one distinct delivered order.
- **Customer state:** the most common state across a customer's orders (the mode).
- **Uncategorized:** items with no product category are kept as "Uncategorized" instead of being dropped.

## How the data flows
```
raw Kaggle CSVs  ->  prepare_data.py  ->  data_summary/*.csv  ->  app.py (Dash)
 (your computer)      (run once)           (small, committed)      (runs on Render)
```
The raw tables are large, so the heavy work happens once in `prepare_data.py`. The app reads only the small summary files. That keeps startup fast, needs no secret token on the web server, and keeps customer-level data out of the repo (the top spenders are shown as "Customer #1", "Customer #2", and so on).

## Project structure
```
olist-revenue-retention/
├── app.py                  # Dash app
├── pipeline.py             # the single revenue definition and the data logic
├── prepare_data.py         # builds data_summary/ from the raw tables
├── data_summary/           # small summary files the app reads
├── requirements.txt        # what the app needs
├── requirements-prep.txt   # extra packages for prepare_data.py
└── data/                   # raw Kaggle CSVs (not committed)
```

## Run it locally
```bash
pip install -r requirements.txt
python app.py
```
Then open http://127.0.0.1:8050

To rebuild the summary files from the raw data, put the six Kaggle CSV files in `data/` and run:
```bash
pip install -r requirements-prep.txt
python prepare_data.py --source local --data-dir data
```

## Deploy on Render
- **Service type:** Web Service, connected to this GitHub repo
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `gunicorn app:server`
- No environment variables or secrets are needed.

## Tools
Python (pandas, Plotly, Dash), Render
