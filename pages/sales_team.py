"""Sales team: rep scorecards with volume-normalised metrics."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src import descriptive_analytics as da
from src.ui import BLUE, ORANGE, detail_grid, get_master, kpi_cards, money, page_header, pct, style

master, _ = get_master()
page_header("Sales team", "Rep scorecards. Compare win rate and revenue per closed deal, not just total revenue, "
                          "because reps handle different volumes.")

office = st.segmented_control("Office", ["All"] + sorted(master["regional_office"].dropna().unique()), default="All")
df = master if office in (None, "All") else master[master["regional_office"] == office]
reps = da.rep_performance(df)

best = reps.loc[reps["won_revenue"].idxmax()]
eff = reps[reps["won"] + reps["lost"] >= 30].sort_values("win_rate", ascending=False)
kpi_cards([
    ("Active reps", f"{len(reps)}", f"{reps['manager'].nunique()} managers"),
    ("Top by revenue", best["sales_agent"], money(best["won_revenue"])),
    ("Top by win rate", eff.iloc[0]["sales_agent"] if len(eff) else "-",
     f"{pct(eff.iloc[0]['win_rate'])} (≥30 closed)" if len(eff) else ""),
    ("Team win rate", pct(df["is_won"].sum() / df["is_closed"].sum()) if df["is_closed"].any() else "-",
     f"{int(df['is_closed'].sum()):,} closed deals"),
])

c1, c2 = st.columns([1.3, 1])
with c1, st.container(border=True):
    r = reps.sort_values("won_revenue")
    fig = go.Figure(go.Bar(x=r["won_revenue"], y=r["sales_agent"], orientation="h", marker=dict(color=BLUE, cornerradius=3),
                           customdata=r[["won", "win_rate", "regional_office"]].values,
                           hovertemplate="%{y} (%{customdata[2]})<br>Won revenue $%{x:,.0f}<br>%{customdata[0]:,} won"
                                         " · win rate %{customdata[1]:.1%}<extra></extra>"))
    fig.update_xaxes(tickprefix="$", tickformat="~s")
    st.plotly_chart(style(fig, max(320, 22 * len(r) + 60), "Won revenue by rep"), width="stretch")
with c2, st.container(border=True):
    fig = go.Figure(go.Scatter(
        x=reps["won"] + reps["lost"], y=reps["win_rate"], mode="markers", text=reps["sales_agent"],
        marker=dict(size=12, color=BLUE, line=dict(color="white", width=2)),
        customdata=reps[["won_revenue"]].values,
        hovertemplate="%{text}<br>%{x:,} closed deals<br>Win rate %{y:.1%}<br>Won revenue $%{customdata[0]:,.0f}"
                      "<extra></extra>"))
    overall = df["is_won"].sum() / max(df["is_closed"].sum(), 1)
    fig.add_hline(y=overall, line=dict(color=ORANGE, width=1.5),
                  annotation_text=f"team average {overall:.1%}", annotation_position="top left")
    fig.update_xaxes(title="Closed deals (volume)")
    fig.update_yaxes(title="Win rate", tickformat=".0%")
    st.plotly_chart(style(fig, max(320, 22 * len(reps) + 60), "Volume vs win rate"), width="stretch")

st.markdown("**Scorecard**: click a rep for details")
cols = ["sales_agent", "manager", "regional_office", "opportunities", "open", "won", "lost", "win_rate",
        "win_rate_vs_office_pp", "won_revenue", "avg_won_deal", "revenue_per_closed_deal", "open_pipeline_est_value"]
view = reps.sort_values("won_revenue", ascending=False)
event = st.dataframe(view[cols], hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                     key="rep_table",
                     column_config={
                         "sales_agent": "rep", "regional_office": "office",
                         "win_rate": st.column_config.ProgressColumn("win rate", format="%.2f", min_value=0.0, max_value=1.0),
                         "win_rate_vs_office_pp": st.column_config.NumberColumn("vs office (pp)", format="%+.1f"),
                         "won_revenue": st.column_config.NumberColumn("won revenue", format="$%.0f"),
                         "avg_won_deal": st.column_config.NumberColumn("avg won deal", format="$%.0f"),
                         "revenue_per_closed_deal": st.column_config.NumberColumn("revenue / closed deal", format="$%.0f"),
                         "open_pipeline_est_value": st.column_config.NumberColumn("open pipeline (est.)", format="$%.0f"),
                     })

rows = event.selection.rows if event and event.selection else []
if rows:
    rep = view.iloc[rows[0]]
    deals = df[df["sales_agent"] == rep["sales_agent"]]
    with st.container(border=True):
        st.markdown(f"### {rep['sales_agent']}")
        st.caption(f"{rep['regional_office']} office · reports to {rep['manager']}")
        detail_grid([("Deals", f"{rep['opportunities']:,}"), ("Open", f"{rep['open']:,}"),
                     ("Won / lost", f"{rep['won']:,} / {rep['lost']:,}"), ("Win rate", pct(rep["win_rate"])),
                     ("Won revenue", money(rep["won_revenue"])), ("Avg won deal", money(rep["avg_won_deal"]))])
        m = da.revenue_by_period(deals, "M")
        if not m.empty:
            fig = go.Figure(go.Bar(x=m["period"], y=m["won_revenue"], marker=dict(color=BLUE, cornerradius=3),
                                   hovertemplate="%{x|%b %Y}<br>$%{y:,.0f}<extra></extra>"))
            fig.update_yaxes(tickprefix="$", tickformat="~s")
            fig.update_xaxes(dtick="M1", tickformat="%b\n%Y")
            st.plotly_chart(style(fig, 260, "Monthly won revenue"), width="stretch")
