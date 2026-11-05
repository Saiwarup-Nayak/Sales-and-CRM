"""Accounts: customer companies with their deal history."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src import crm_store
from src import descriptive_analytics as da
from src.preprocessing import NOT_ASSIGNED
from src.ui import (OUTCOME_COLORS, detail_grid, get_master, kpi_cards, money, page_header, pct, style)

master, _ = get_master()
accounts = crm_store.read_tables()["accounts"]
page_header("Accounts", f"{len(accounts):,} customer companies. Click a row to open the account.")

summary = da.summarise_by(master[master["account"] != NOT_ASSIGNED], "account")
tbl = accounts.merge(summary[["account", "opportunities", "open", "won", "lost", "win_rate", "won_revenue",
                              "open_pipeline_est_value"]], on="account", how="left")
tbl[["opportunities", "open", "won", "lost"]] = tbl[["opportunities", "open", "won", "lost"]].fillna(0).astype(int)
tbl["won_revenue"] = tbl["won_revenue"].fillna(0)

f1, f2 = st.columns([2, 1])
q = f1.text_input("Search accounts", placeholder="Name, location, parent company...", label_visibility="collapsed")
sectors = f2.multiselect("Sector", sorted(tbl["sector"].dropna().unique()), placeholder="All sectors",
                         label_visibility="collapsed")
view = tbl
if sectors:
    view = view[view["sector"].isin(sectors)]
if q:
    view = view[view[["account", "office_location", "subsidiary_of", "sector"]].astype(str)
                .apply(lambda c: c.str.contains(q, case=False, na=False)).any(axis=1)]
view = view.sort_values("won_revenue", ascending=False)

kpi_cards([
    ("Accounts", f"{len(view):,}", f"{view['sector'].nunique()} sectors"),
    ("Won revenue", money(view["won_revenue"].sum()), f"{view['won'].sum():,} won deals"),
    ("Top account", view.iloc[0]["account"] if len(view) else "-",
     money(view.iloc[0]["won_revenue"]) if len(view) else ""),
    ("Unassigned deals", f"{int((master['account'] == NOT_ASSIGNED).sum()):,}", "open deals with no account yet"),
], accent_first=False)

cols = ["account", "sector", "office_location", "employees", "revenue", "year_established", "subsidiary_of",
        "opportunities", "won", "win_rate", "won_revenue", "open_pipeline_est_value", "source"]
event = st.dataframe(view[cols], hide_index=True, width="stretch", height=400, on_select="rerun",
                     selection_mode="single-row", key="acc_table",
                     column_config={
                         "office_location": "HQ", "subsidiary_of": "parent",
                         "revenue": st.column_config.NumberColumn("revenue ($M)", format="%.1f"),
                         "year_established": st.column_config.NumberColumn("founded", format="%d"),
                         "employees": st.column_config.NumberColumn(format="%d"),
                         "win_rate": st.column_config.ProgressColumn("win rate", format="%.2f", min_value=0.0, max_value=1.0),
                         "won_revenue": st.column_config.NumberColumn("won revenue", format="$%.0f"),
                         "open_pipeline_est_value": st.column_config.NumberColumn("open pipeline (est.)", format="$%.0f"),
                     })

rows = event.selection.rows if event and event.selection else []
if rows:
    a = view.iloc[rows[0]]
    deals = master[master["account"] == a["account"]]
    with st.container(border=True):
        st.markdown(f"### {a['account']}")
        st.caption(f"{str(a['sector']).title()} · {a['office_location']}"
                   + (f" · subsidiary of {a['subsidiary_of']}" if isinstance(a["subsidiary_of"], str) else ""))
        detail_grid([("Employees", f"{a['employees']:,.0f}"), ("Revenue", f"${a['revenue']:,.1f}M"),
                     ("Founded", f"{a['year_established']:.0f}"), ("Deals", f"{a['opportunities']:,}"),
                     ("Win rate", pct(a["win_rate"])), ("Won revenue", money(a["won_revenue"]))])
        if deals.empty:
            st.info("No opportunities for this account yet.")
        else:
            c1, c2 = st.columns([1, 1.4])
            with c1:
                p = deals.groupby(["product", "outcome"]).size().unstack(fill_value=0)
                fig = go.Figure()
                for o in ["Won", "Lost", "Open"]:
                    if o in p:
                        fig.add_bar(name=o, y=p.index, x=p[o], orientation="h",
                                    marker=dict(color=OUTCOME_COLORS[o], line=dict(color="white", width=2)),
                                    hovertemplate="%{y}: %{x} " + o.lower() + "<extra></extra>")
                fig.update_layout(barmode="stack")
                st.plotly_chart(style(fig, 300, "Deals by product and outcome"), width="stretch")
            with c2:
                st.dataframe(deals.sort_values("engage_date", ascending=False)[
                    ["opportunity_id", "deal_stage", "product", "sales_agent", "engage_date", "close_date", "close_value"]],
                    hide_index=True, width="stretch", height=300,
                    column_config={"engage_date": st.column_config.DateColumn("engaged"),
                                   "close_date": st.column_config.DateColumn("closed"),
                                   "close_value": st.column_config.NumberColumn("value", format="$%.0f")})
