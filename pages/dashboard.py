"""Dashboard: headline KPIs and charts, filtered by close date, office and product."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import descriptive_analytics as da
from src.ui import (BLUE, ORANGE, STAGE_COLORS, get_master, kpi_cards, master_with_scores, money, page_header, pct,
                    style)

master, snapshot = get_master()
page_header("Dashboard", f"Sales performance across {len(master):,} opportunities · data through {snapshot:%d %b %Y}")

# ---------------------------------------------------------------------------
# Filters (one row, scoping everything below)
# ---------------------------------------------------------------------------
closed_dates = master["close_date"].dropna()
dmin, dmax = closed_dates.min().date(), closed_dates.max().date()
f1, f2, f3 = st.columns([1.3, 1, 1])
rng = f1.date_input("Close date range", (dmin, dmax), min_value=dmin, max_value=dmax, format="DD/MM/YYYY")
offices = f2.multiselect("Regional office", sorted(master["regional_office"].dropna().unique()), placeholder="All offices")
products = f3.multiselect("Product", sorted(master["product"].unique()), placeholder="All products")

df = master
if offices:
    df = df[df["regional_office"].isin(offices)]
if products:
    df = df[df["product"].isin(products)]
if isinstance(rng, tuple) and len(rng) == 2:
    start, end = pd.Timestamp(rng[0]), pd.Timestamp(rng[1])
    df = df[df["is_open"] | df["close_date"].between(start, end)]
st.caption("The date range applies to closed deals. Open deals have no close date, so they always count toward "
           "the pipeline.")

if df.empty:
    st.info("No opportunities match these filters.")
    st.stop()

k = da.compute_kpis(df)
kpi_cards([
    ("Won revenue", money(k["won_revenue"]), f"{k['won_deals']:,} won deals"),
    ("Win rate", pct(k["win_rate"]), f"of {k['closed_opportunities']:,} closed deals"),
    ("Avg won deal", money(k["avg_won_deal"]), "realised value"),
    ("Open pipeline (est.)", money(k["open_pipeline_est_value"]), f"{k['open_opportunities']:,} open deals at list price"),
    ("Avg sales cycle", f"{k['avg_sales_cycle_days']:.0f} days" if k["closed_opportunities"] else "-", "engage → close"),
    ("Active reps", f"{k['active_reps']}", "with at least one deal"),
])

# ---------------------------------------------------------------------------
# Row 1: revenue trend + pipeline by stage
# ---------------------------------------------------------------------------
c1, c2 = st.columns([1.6, 1])
with c1, st.container(border=True):
    m = da.revenue_by_period(df, "M")
    fig = go.Figure(go.Scatter(x=m["period"], y=m["won_revenue"], mode="lines+markers", fill="tozeroy",
                               line=dict(color=BLUE, width=2), fillcolor="rgba(42,120,214,0.10)",
                               marker=dict(size=8, color=BLUE, line=dict(color="white", width=2)),
                               customdata=m[["won", "win_rate"]].values,
                               hovertemplate="%{x|%b %Y}<br>Won revenue $%{y:,.0f}<br>%{customdata[0]:,} won deals"
                                             "<br>Win rate %{customdata[1]:.1%}<extra></extra>"))
    fig.update_yaxes(tickprefix="$", tickformat="~s", rangemode="tozero")
    fig.update_xaxes(dtick="M1", tickformat="%b\n%Y")
    st.plotly_chart(style(fig, 330, "Monthly won revenue"), width="stretch")

with c2, st.container(border=True):
    f = da.funnel(df)["snapshot"]
    fig = go.Figure(go.Bar(x=f["opportunities"], y=f["stage"], orientation="h",
                           marker=dict(color=[STAGE_COLORS[s] for s in f["stage"]], cornerradius=4),
                           text=[f"{n:,}" for n in f["opportunities"]], textposition="outside", cliponaxis=False,
                           customdata=f[["share", "est_value"]].values,
                           hovertemplate="%{y}: %{x:,} deals (%{customdata[0]:.1%})<br>"
                                         "Value $%{customdata[1]:,.0f}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(showticklabels=False, showgrid=False)
    st.plotly_chart(style(fig, 330, "Deals by stage"), width="stretch")

# ---------------------------------------------------------------------------
# Row 2: product revenue + office win rate
# ---------------------------------------------------------------------------
c1, c2 = st.columns(2)
with c1, st.container(border=True):
    p = da.summarise_by(df, "product").sort_values("won_revenue")
    fig = go.Figure(go.Bar(x=p["won_revenue"], y=p["product"], orientation="h", marker=dict(color=BLUE, cornerradius=4),
                           text=[money(v) for v in p["won_revenue"]], textposition="outside", cliponaxis=False,
                           customdata=p[["won", "win_rate", "avg_won_deal"]].values,
                           hovertemplate="%{y}<br>Won revenue $%{x:,.0f}<br>%{customdata[0]:,} won · win rate "
                                         "%{customdata[1]:.1%}<br>Avg deal $%{customdata[2]:,.0f}<extra></extra>"))
    fig.update_xaxes(tickprefix="$", tickformat="~s")
    st.plotly_chart(style(fig, 330, "Won revenue by product"), width="stretch")

with c2, st.container(border=True):
    o = da.summarise_by(df, "regional_office").sort_values("win_rate", ascending=False)
    fig = go.Figure(go.Bar(x=o["regional_office"], y=o["win_rate"], marker=dict(color=BLUE, cornerradius=4),
                           error_y=dict(type="data", symmetric=False, array=o["win_rate_hi"] - o["win_rate"],
                                        arrayminus=o["win_rate"] - o["win_rate_lo"], color="#898781", thickness=1.2),
                           text=[pct(v) for v in o["win_rate"]], textposition="inside", insidetextanchor="end",
                           textfont=dict(color="white"),
                           customdata=o[["won", "lost", "won_revenue"]].values,
                           hovertemplate="%{x}<br>Win rate %{y:.1%}<br>%{customdata[0]:,} won / %{customdata[1]:,} lost"
                                         "<br>Won revenue $%{customdata[2]:,.0f}<extra></extra>"))
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    st.plotly_chart(style(fig, 330, "Win rate by regional office (95% CI)"), width="stretch")

# ---------------------------------------------------------------------------
# Row 3: top reps + won vs lost per month
# ---------------------------------------------------------------------------
c1, c2 = st.columns(2)
with c1, st.container(border=True):
    r = da.summarise_by(df, "sales_agent").nlargest(10, "won_revenue").sort_values("won_revenue")
    fig = go.Figure(go.Bar(x=r["won_revenue"], y=r["sales_agent"], orientation="h", marker=dict(color=BLUE, cornerradius=4),
                           text=[money(v) for v in r["won_revenue"]], textposition="outside", cliponaxis=False,
                           customdata=r[["won", "win_rate"]].values,
                           hovertemplate="%{y}<br>Won revenue $%{x:,.0f}<br>%{customdata[0]:,} won · win rate "
                                         "%{customdata[1]:.1%}<extra></extra>"))
    fig.update_xaxes(tickprefix="$", tickformat="~s")
    st.plotly_chart(style(fig, 360, "Top 10 sales reps by won revenue"), width="stretch")

with c2, st.container(border=True):
    fig = go.Figure()
    fig.add_bar(name="Won", x=m["period"], y=m["won"], marker=dict(color=BLUE, cornerradius=3),
                hovertemplate="%{x|%b %Y}<br>%{y:,} won<extra></extra>")
    fig.add_bar(name="Lost", x=m["period"], y=m["lost"], marker=dict(color=ORANGE, cornerradius=3),
                hovertemplate="%{x|%b %Y}<br>%{y:,} lost<extra></extra>")
    fig.update_layout(barmode="group", bargroupgap=0.08)
    fig.update_xaxes(dtick="M1", tickformat="%b\n%Y")
    st.plotly_chart(style(fig, 360, "Deals won vs lost per month"), width="stretch")

# ---------------------------------------------------------------------------
# Row 4: sector revenue + top open deals
# ---------------------------------------------------------------------------
c1, c2 = st.columns(2)
with c1, st.container(border=True):
    s = da.summarise_by(df[df["account_known"]], "sector").sort_values("won_revenue", ascending=False)
    fig = go.Figure(go.Bar(x=s["sector"].str.title(), y=s["won_revenue"], marker=dict(color=BLUE, cornerradius=4),
                           customdata=s[["won", "win_rate"]].values,
                           hovertemplate="%{x}<br>Won revenue $%{y:,.0f}<br>%{customdata[0]:,} won · win rate "
                                         "%{customdata[1]:.1%}<extra></extra>"))
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    st.plotly_chart(style(fig, 360, "Won revenue by customer sector"), width="stretch")

with c2, st.container(border=True):
    st.markdown("**Largest open deals**")
    scored = master_with_scores().set_index("opportunity_id")["win_probability"]
    top = df[df["is_open"]].nlargest(10, "est_open_value").copy()
    top["win_probability"] = top["opportunity_id"].map(scored)
    st.dataframe(top[["opportunity_id", "account", "product", "deal_stage", "sales_agent", "est_open_value",
                      "win_probability"]],
                 hide_index=True, width="stretch", height=300,
                 column_config={"est_open_value": st.column_config.NumberColumn("est. value", format="$%.0f"),
                                "win_probability": st.column_config.ProgressColumn(
                                    "win prob.", format="%.2f", min_value=0.0, max_value=1.0,
                                    help="Model estimate. On this dataset the model is no better than chance "
                                         "(see Data review › Conversion prediction)."),
                                "deal_stage": "stage", "sales_agent": "rep"})
