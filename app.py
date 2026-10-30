"""
Olist Revenue Drivers & Customer Retention Audit  (built with Dash)

WHAT THE APP READS
    The small summary files in data_summary/, made by prepare_data.py.
    No raw data and no secret token are needed to run it.

HOW TO RUN ON YOUR COMPUTER
    pip install -r requirements.txt
    python app.py
    Open http://127.0.0.1:8050

HOW A HOSTING SERVICE (RENDER) RUNS IT
    gunicorn app:server

DASH VOCABULARY
    component   A building block of the page (a title, a box, a chart, a dropdown...).
    layout      The tree of components = what the page looks like.
    figure      The chart itself (a Plotly object). dcc.Graph just displays it.
    id          A name that lets a callback find a component.
    callback    A function Dash runs when the user touches a control.
                Input = the control that changed, Output = what gets updated.
"""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dash_table, dcc, html
from dash.dash_table.Format import Format, Group, Scheme

# =====================================================================
# 0. SETTINGS
# =====================================================================
DATA_DIR = Path(__file__).parent / "data_summary"
AUTHOR = "Pascal Ndife"
GITHUB_URL = "https://github.com/leodera/olist-revenue-retention"
QUESTION = "Which categories and states drive the most revenue, and do those customers ever come back to buy again?"
REVENUE_NOTE = "Delivered orders only. Revenue = sum of item price, freight excluded."

NAVY, BLUE, LIGHT, ORANGE, GREY = "#1E3A8A", "#2563EB", "#BFD4FB", "#F97316", "#94A3B8"
TEXT, MUTED, BG, BORDER = "#0F172A", "#64748B", "#F8FAFC", "#E2E8F0"
FONT = "Segoe UI, Roboto, Helvetica, Arial, sans-serif"


# =====================================================================
# 1. LOAD THE SUMMARY FILES
# =====================================================================
def read(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run 'python prepare_data.py' first (see the README).")
    return pd.read_csv(path)


state_all = read("state_summary.csv").sort_values("total_revenue", ascending=False).reset_index(drop=True)
freq_all = read("freq_by_state.csv")
spenders_all = read("top_spenders.csv")
categories = read("category_summary.csv").sort_values("gross_sales", ascending=False).reset_index(drop=True)
recon = json.loads((DATA_DIR / "recon.json").read_text())
ALL_STATE_CODES = list(state_all["customer_state"])


def money(x: float) -> str:
    if x >= 1e6:
        return f"R$ {x / 1e6:.2f}M"
    if x >= 1e3:
        return f"R$ {x / 1e3:.1f}k"
    return f"R$ {x:,.0f}"


def pick(df: pd.DataFrame, selected) -> pd.DataFrame:
    """Rows for the chosen states. Nothing chosen = all states."""
    if not selected:
        return df
    return df[df["customer_state"].isin(selected)]


# =====================================================================
# 2. NUMBERS AND TEXT (every sentence on the page is computed from the data)
# =====================================================================
def kpi_values(selected) -> dict:
    s = pick(state_all, selected)
    buyers = int(s["total_buyers"].sum())
    repeat = int(s["repeat_buyers"].sum())
    orders = int(s["total_orders"].sum())
    return {
        "revenue": float(s["total_revenue"].sum()),
        "buyers": buyers,
        "repeat_rate": repeat / buyers * 100 if buyers else 0.0,
        "avg_orders": orders / buyers if buyers else 0.0,
    }


def state_table(selected) -> pd.DataFrame:
    s = pick(state_all, selected).copy()
    s["repeat_pct"] = s["repeat_buyers"] / s["total_buyers"] * 100
    return s


def geo_finding(selected) -> str:
    s = state_table(selected)
    if len(s) < 4:
        return "Select at least 4 states (or none, for all states) to compare revenue with repeat rate."
    top3 = s.head(3)
    share = top3["total_revenue"].sum() / s["total_revenue"].sum() * 100
    rho = s["total_revenue"].rank().corr(s["repeat_pct"].rank())
    weak = abs(rho) < 0.3
    return (
        f"The top 3 states ({', '.join(top3['customer_state'])}) bring in {share:.1f}% of revenue in this view, "
        f"with repeat rates between {top3['repeat_pct'].min():.1f}% and {top3['repeat_pct'].max():.1f}%. "
        f"Across the {len(s)} states, the rank correlation between revenue and repeat rate is {rho:.2f} "
        + ("(weak), so a bigger market does not mean more loyal customers." if weak
           else "(not weak), so bigger markets tend to differ in loyalty.")
    )


def retention_finding(selected) -> str:
    sp = pick(spenders_all, selected).nlargest(10, "total_spent")
    k = kpi_values(selected)
    if sp.empty:
        return "No customers in this view."
    n = len(sp)
    one_time = int((sp["total_orders"] == 1).sum())
    base = 100 - k["repeat_rate"]
    verdict = (
        "High spend here comes mostly from single large orders, not repeat visits."
        if one_time / n >= 0.5
        else "High spend here comes partly from customers who return."
    )
    return f"{one_time} of the top {n} highest-spending buyers ({one_time / n:.0%}) ordered only once, versus {base:.1f}% of all buyers in this view. {verdict}"


# =====================================================================
# 3. CHARTS
# =====================================================================
def style(fig: go.Figure, title: str, height: int = 380) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0.01, font=dict(size=16, color=TEXT)),
        template="plotly_white",
        height=height,
        margin=dict(l=55, r=30, t=60, b=50),
        font=dict(family=FONT, size=12, color=TEXT),
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    return fig


def fig_categories(top_n: int = 10) -> go.Figure:
    df = categories.head(top_n)
    fig = go.Figure(
        go.Bar(
            x=df["gross_sales"] / 1e6,
            y=df["category"].str.replace("_", " ", regex=False),
            orientation="h",
            marker_color=BLUE,
            text=[f"R$ {v / 1e6:.2f}M" if v >= 1e6 else f"R$ {v / 1e3:.0f}k" for v in df["gross_sales"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Sales: R$ %{x:.2f}M<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="Gross sales (R$ millions)", rangemode="tozero")
    fig.update_layout(margin=dict(l=150, r=70, t=60, b=50))
    return style(fig, f"Top {top_n} categories by delivered sales (item price)", height=max(340, 28 * top_n + 120))


def fig_state_bar(selected) -> go.Figure:
    df = state_table(selected).head(10)
    fig = go.Figure(
        go.Bar(
            x=df["total_revenue"] / 1e6,
            y=df["customer_state"],
            orientation="h",
            marker_color=BLUE,
            text=[money(v) for v in df["total_revenue"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Revenue: R$ %{x:.2f}M<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="Delivered revenue (R$ millions)", rangemode="tozero")
    fig.update_layout(margin=dict(l=55, r=70, t=60, b=50))
    return style(fig, "Top 10 states by delivered revenue (item price)", height=420)


def fig_state_scatter(selected) -> go.Figure:
    df = state_table(selected)
    fig = go.Figure(
        go.Scatter(
            x=df["total_revenue"] / 1e6,
            y=df["repeat_pct"],
            mode="markers+text",
            text=df["customer_state"],
            textposition="top center",
            textfont=dict(size=10),
            marker=dict(size=[max(8, (b ** 0.5) / 4) for b in df["total_buyers"]], color=BLUE, opacity=0.8,
                        line=dict(width=1, color="white")),
            hovertext=[
                f"<b>{r.customer_state}</b><br>Revenue: {money(r.total_revenue)}<br>Repeat rate: {r.repeat_pct:.2f}%"
                f"<br>Buyers: {int(r.total_buyers):,}"
                for r in df.itertuples()
            ],
            hoverinfo="text",
        )
    )
    fig.update_xaxes(title_text="Delivered revenue (R$ millions, log scale)", type="log")
    fig.update_yaxes(title_text="Repeat buyers (% of buyers)", rangemode="tozero")
    return style(fig, "State revenue vs. repeat purchase rate (bubble size = buyers)", height=420)


def fig_spenders(selected) -> go.Figure:
    sp = pick(spenders_all, selected).nlargest(10, "total_spent").reset_index(drop=True)
    fig = go.Figure(
        go.Bar(
            x=sp["total_spent"],
            y=[f"Customer #{i + 1} ({r.customer_state})" for i, r in enumerate(sp.itertuples())],
            orientation="h",
            marker=dict(color=sp["total_orders"], colorscale="Blues", cmin=0,
                        colorbar=dict(title="Orders placed")),
            text=[f"R$ {v:,.0f}" for v in sp["total_spent"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Spend: R$ %{x:,.2f}<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="Lifetime spend, item price (R$)", rangemode="tozero")
    fig.update_layout(margin=dict(l=150, r=80, t=60, b=50))
    return style(fig, "Top 10 highest-spending buyers (color = lifetime orders)", height=420)


# =====================================================================
# 4. TABLE ROWS
# =====================================================================
def category_rows(top_n: int) -> list:
    df = categories.head(top_n).copy()
    df["category"] = df["category"].str.replace("_", " ", regex=False)
    return df.round(2).to_dict("records")


def freq_rows(selected) -> list:
    f = pick(freq_all, selected).groupby("lifetime_orders", as_index=False)["buyers"].sum().sort_values("lifetime_orders")
    total = f["buyers"].sum()
    f["share"] = (f["buyers"] / total * 100).round(2) if total else 0.0
    return f.to_dict("records")


# =====================================================================
# 5. PAGE PIECES
# =====================================================================
CARD = dict(background="white", border=f"1px solid {BORDER}", borderRadius="12px", padding="14px 18px",
            boxShadow="0 1px 2px rgba(15, 23, 42, 0.05)")
ROW = dict(display="flex", gap="16px", flexWrap="wrap", marginBottom="16px")
HALF = dict(flex="1 1 420px", minWidth="0")
LABEL = dict(color=MUTED, fontSize="13px", padding="6px 6px 0")
INT_FMT = Format(group=Group.yes, precision=0, scheme=Scheme.fixed)
MONEY_FMT = Format(group=Group.yes, precision=2, scheme=Scheme.fixed)


def kpi(title: str, value: str, sub: str = "") -> html.Div:
    return html.Div(
        [
            html.Div(title, style=dict(color=MUTED, fontSize="13px")),
            html.Div(value, style=dict(fontSize="28px", fontWeight="700", color=NAVY)),
            html.Div(sub, style=dict(color=MUTED, fontSize="12px")),
        ],
        style={**CARD, "flex": "1 1 190px", "minWidth": "0"},
    )


def kpi_cards(selected) -> list:
    k = kpi_values(selected)
    return [
        kpi("Delivered revenue", money(k["revenue"]), "item price, freight excluded"),
        kpi("Unique buyers", f"{k['buyers']:,}", "distinct customers"),
        kpi("Repeat rate", f"{k['repeat_rate']:.2f}%", "buyers with 2+ delivered orders"),
        kpi("Avg orders per buyer", f"{k['avg_orders']:.2f}", "delivered orders"),
    ]


def text_box(box_id: str, text: str) -> html.Div:
    return html.Div(
        text,
        id=box_id,
        style={**CARD, "background": "#EFF6FF", "borderColor": "#BFDBFE", "boxShadow": "none",
               "lineHeight": "1.6", "fontSize": "14px", "marginTop": "4px"},
    )


def graph_card(graph_id: str, figure: go.Figure) -> html.Div:
    return html.Div(
        dcc.Graph(id=graph_id, figure=figure, config=dict(displayModeBar=False), responsive=True),
        style={**CARD, "padding": "6px"},
    )


def table(table_id: str, columns: list, data: list, page_size: int = 12) -> dash_table.DataTable:
    numeric = [c["id"] for c in columns if c.get("type") == "numeric"]
    return dash_table.DataTable(
        id=table_id,
        columns=columns,
        data=data,
        sort_action="native",
        page_size=page_size,
        style_table=dict(overflowX="auto"),
        style_header=dict(backgroundColor="#EFF6FF", fontWeight="700", color=NAVY, border="none"),
        style_cell=dict(textAlign="left", padding="8px 10px", fontFamily=FONT, fontSize="13px",
                        border="none", borderBottom=f"1px solid {BORDER}", minWidth="90px"),
        style_cell_conditional=[{"if": {"column_id": c}, "textAlign": "right"} for c in numeric],
    )


def recon_card() -> html.Details:
    rows = [
        {"measure": "Item price, delivered orders (headline revenue)", "value": recon["item_price"]},
        {"measure": "Freight charged", "value": recon["freight"]},
        {"measure": "Item price + freight", "value": recon["item_price"] + recon["freight"]},
        {"measure": "Payments collected (payment_value)", "value": recon["payment_value"]},
        {"measure": "Payments minus (item price + freight)",
         "value": recon["payment_value"] - recon["item_price"] - recon["freight"]},
    ]
    cols = [dict(name="Measure", id="measure"), dict(name="R$", id="value", type="numeric", format=MONEY_FMT)]
    return html.Details(
        [
            html.Summary("Revenue reconciliation: item price vs. cash collected (platform-wide)",
                         style=dict(cursor="pointer", fontWeight="600", color=NAVY)),
            html.Div(style=dict(height="8px")),
            table("recon-table", cols, rows, page_size=10),
            html.Div(
                "Payments collected are higher than item price because they also include freight and any "
                "installment interest. This dashboard reports item price, so the category, state and customer "
                "views all add up to the same number.",
                style=dict(color=MUTED, fontSize="13px", paddingTop="8px"),
            ),
        ],
        style={**CARD, "marginBottom": "16px"},
    )


def categories_page() -> html.Div:
    cols = [
        dict(name="Category", id="category"),
        dict(name="Gross sales (R$)", id="gross_sales", type="numeric", format=MONEY_FMT),
        dict(name="Units sold", id="units_sold", type="numeric", format=INT_FMT),
        dict(name="Avg item price (R$)", id="avg_item_price", type="numeric", format=MONEY_FMT),
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Show top N categories (covers all states):", style=LABEL),
                    dcc.Slider(id="top-n", min=5, max=25, step=1, value=10,
                               marks={5: "5", 10: "10", 15: "15", 20: "20", 25: "25"}),
                ],
                style={**CARD, "padding": "10px", "marginBottom": "16px"},
            ),
            graph_card("category-bar", fig_categories(10)),
            html.Div(style=dict(height="16px")),
            html.Div(
                [html.Div("Category data", style=dict(fontWeight="700", color=NAVY, marginBottom="6px")),
                 table("category-table", cols, category_rows(10))],
                style=CARD,
            ),
        ],
        style=dict(padding="16px 0"),
    )


def geo_page() -> html.Div:
    return html.Div(
        [
            html.Div(
                [html.Div(graph_card("geo-bar", fig_state_bar(None)), style=HALF),
                 html.Div(graph_card("geo-scatter", fig_state_scatter(None)), style=HALF)],
                style=ROW,
            ),
            text_box("geo-finding", geo_finding(None)),
        ],
        style=dict(padding="16px 0"),
    )


def retention_page() -> html.Div:
    cols = [
        dict(name="Lifetime orders", id="lifetime_orders", type="numeric", format=INT_FMT),
        dict(name="Total buyers", id="buyers", type="numeric", format=INT_FMT),
        dict(name="Share of buyers (%)", id="share", type="numeric", format=MONEY_FMT),
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [html.Div("Order frequency", style=dict(fontWeight="700", color=NAVY, marginBottom="6px")),
                         table("freq-table", cols, freq_rows(None), page_size=10)],
                        style={**CARD, "flex": "1 1 320px", "minWidth": "0"},
                    ),
                    html.Div(graph_card("spenders-bar", fig_spenders(None)), style={"flex": "2 1 480px", "minWidth": "0"}),
                ],
                style=ROW,
            ),
            text_box("retention-finding", retention_finding(None)),
        ],
        style=dict(padding="16px 0"),
    )


# =====================================================================
# 6. THE APP: layout + callbacks
# =====================================================================
app = Dash(
    __name__,
    title="Olist Revenue & Retention Audit",
    update_title=None,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server  # Render (gunicorn) looks for this

app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>body { margin: 0; background: #F8FAFC; }</style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""

TAB = dict(padding="10px 18px", border="none", borderBottom=f"2px solid {BORDER}", background="transparent",
           color=MUTED, fontWeight="600", fontFamily=FONT)
TAB_SELECTED = {**TAB, "borderBottom": f"3px solid {BLUE}", "color": NAVY}

warning = []
if abs(recon["state_total"] - recon["item_price"]) > 0.5:
    warning = [html.Div(
        "State totals and item-level totals differ. Some delivered orders may be missing a matching customer record.",
        style={**CARD, "background": "#FEF3C7", "borderColor": "#FDE68A", "marginBottom": "16px"},
    )]

app.layout = html.Div(
    [
        html.Div(
            [
                html.Div(
                    [
                        html.H1("Olist Revenue Drivers & Customer Retention Audit",
                                style=dict(margin="0", color=NAVY, fontSize="26px")),
                        html.Div(QUESTION, style=dict(color=MUTED, margin="4px 0 0", fontSize="14px")),
                        html.Div(REVENUE_NOTE, style=dict(color=MUTED, margin="2px 0 0", fontSize="12px")),
                    ],
                    style=dict(flex="1 1 420px"),
                ),
                html.A("View code on GitHub ↗", href=GITHUB_URL, target="_blank",
                       style=dict(color=BLUE, fontWeight="600", fontSize="14px", textDecoration="none",
                                  border=f"1px solid {BLUE}", borderRadius="999px", padding="6px 14px",
                                  whiteSpace="nowrap")),
            ],
            style=dict(display="flex", justifyContent="space-between", alignItems="flex-start",
                       gap="12px", flexWrap="wrap", marginBottom="14px"),
        ),
        *warning,
        html.Div(
            [
                html.Div("Filter by customer state (empty = all states). Applies to the cards and to the "
                         "Geographic and Retention tabs.", style=LABEL),
                dcc.Dropdown(id="state-filter", options=[{"label": s, "value": s} for s in sorted(ALL_STATE_CODES)],
                             value=[], multi=True, placeholder="All states"),
            ],
            style={**CARD, "padding": "10px", "marginBottom": "16px"},
        ),
        html.Div(kpi_cards(None), id="kpi-row", style=ROW),
        recon_card(),
        dcc.Tabs(
            id="tabs",
            value="categories",
            children=[
                dcc.Tab(label="Product Categories", value="categories", children=categories_page(),
                        style=TAB, selected_style=TAB_SELECTED),
                dcc.Tab(label="Geographic Concentration", value="geo", children=geo_page(),
                        style=TAB, selected_style=TAB_SELECTED),
                dcc.Tab(label="Customer Retention", value="retention", children=retention_page(),
                        style=TAB, selected_style=TAB_SELECTED),
            ],
        ),
        html.Div(
            f"Data: Olist Brazilian E-Commerce dataset (Kaggle). Built with Python, Dash and Plotly by {AUTHOR}.",
            style=dict(color=MUTED, fontSize="12px", textAlign="center", padding="12px 0 4px"),
        ),
    ],
    style=dict(maxWidth="1300px", margin="0 auto", padding="20px", fontFamily=FONT, color=TEXT),
)


# Callback 1: the state filter updates the four headline cards
@app.callback(Output("kpi-row", "children"), Input("state-filter", "value"))
def update_kpis(selected):
    return kpi_cards(selected)


# Callback 2: the slider updates the category chart and its table
@app.callback(Output("category-bar", "figure"), Output("category-table", "data"), Input("top-n", "value"))
def update_categories(top_n):
    n = int(top_n or 10)
    return fig_categories(n), category_rows(n)


# Callback 3: the state filter updates the geographic charts and the finding
@app.callback(
    Output("geo-bar", "figure"), Output("geo-scatter", "figure"), Output("geo-finding", "children"),
    Input("state-filter", "value"),
)
def update_geo(selected):
    return fig_state_bar(selected), fig_state_scatter(selected), geo_finding(selected)


# Callback 4: the state filter updates the retention table, chart and finding
@app.callback(
    Output("freq-table", "data"), Output("spenders-bar", "figure"), Output("retention-finding", "children"),
    Input("state-filter", "value"),
)
def update_retention(selected):
    return freq_rows(selected), fig_spenders(selected), retention_finding(selected)


if __name__ == "__main__":
    app.run(debug=True)  # debug=True is for your own computer; Render uses gunicorn instead
