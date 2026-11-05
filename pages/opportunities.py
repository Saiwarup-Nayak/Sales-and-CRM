"""Opportunities: searchable list of every deal with a detail view."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.ui import detail_grid, kpi_cards, master_with_scores, money, page_header, pct, stage_pill

df_all = master_with_scores()
page_header("Opportunities", "Every deal in the pipeline. Click a row to see its details.")

f1, f2, f3, f4 = st.columns([1.6, 1.2, 1, 1])
q = f1.text_input("Search", placeholder="ID, account, rep, product...", label_visibility="collapsed")
stages = f2.pills("Stage", ["Prospecting", "Engaging", "Won", "Lost"], selection_mode="multi",
                  label_visibility="collapsed")
rep = f3.selectbox("Rep", ["All reps"] + sorted(df_all["sales_agent"].unique()), label_visibility="collapsed")
product = f4.selectbox("Product", ["All products"] + sorted(df_all["product"].unique()), label_visibility="collapsed")

df = df_all
if stages:
    df = df[df["deal_stage"].isin(stages)]
if rep != "All reps":
    df = df[df["sales_agent"] == rep]
if product != "All products":
    df = df[df["product"] == product]
if q:
    cols = ["opportunity_id", "account", "sales_agent", "product", "sector", "deal_stage"]
    df = df[df[cols].astype(str).apply(lambda c: c.str.contains(q, case=False, na=False)).any(axis=1)]

closed = df["is_closed"].sum()
kpi_cards([
    ("Deals shown", f"{len(df):,}", f"of {len(df_all):,}"),
    ("Open", f"{int(df['is_open'].sum()):,}", money(df["est_open_value"].sum()) + " est. value"),
    ("Won", f"{int(df['is_won'].sum()):,}", money(df["won_revenue"].sum()) + " revenue"),
    ("Win rate", pct(df["is_won"].sum() / closed) if closed else "-", f"{int(closed):,} closed"),
], accent_first=False)

view = df.sort_values(["is_open", "engage_date"], ascending=[False, False])
cols = ["opportunity_id", "deal_stage", "account", "product", "sales_agent", "regional_office", "engage_date",
        "close_date", "close_value", "est_open_value", "win_probability", "source"]
event = st.dataframe(
    view[cols], hide_index=True, width="stretch", height=430, on_select="rerun", selection_mode="single-row",
    key="opp_table",
    column_config={
        "opportunity_id": "ID", "deal_stage": "stage", "sales_agent": "rep", "regional_office": "office",
        "engage_date": st.column_config.DateColumn("engaged", format="DD MMM YYYY"),
        "close_date": st.column_config.DateColumn("closed", format="DD MMM YYYY"),
        "close_value": st.column_config.NumberColumn("close value", format="$%.0f"),
        "est_open_value": st.column_config.NumberColumn("est. value (open)", format="$%.0f"),
        "win_probability": st.column_config.ProgressColumn(
            "win prob.", format="%.2f", min_value=0.0, max_value=1.0,
            help="Open deals only. The model is no better than chance on this dataset, so treat it as indicative."),
        "source": st.column_config.TextColumn("source", help="github = original dataset, user = added in this app"),
    })
st.download_button("Download list (CSV)", view[cols].to_csv(index=False).encode(), "opportunities.csv")

rows = event.selection.rows if event and event.selection else []
if rows:
    r = view.iloc[rows[0]]
    with st.container(border=True):
        h1, h2 = st.columns([3, 1])
        h1.markdown(f"### {r['opportunity_id']} &nbsp; {stage_pill(r['deal_stage'])}", unsafe_allow_html=True)
        h1.caption(f"{r['product']} for {r['account']} · handled by {r['sales_agent']}")
        if r["is_open"] and h2.button("Update this deal", icon=":material/edit:", type="primary", width="stretch"):
            st.session_state["edit_opportunity"] = r["opportunity_id"]
            st.switch_page("pages/new_entry.py")
        fmt = lambda d: "-" if pd.isna(d) else f"{d:%d %b %Y}"
        detail_grid([
            ("Account", str(r["account"])), ("Sector", str(r["sector"]).title()),
            ("Product", f"{r['product']} ({r['series']})"), ("List price", money(r["sales_price"])),
            ("Sales rep", str(r["sales_agent"])), ("Manager", str(r["manager"])),
            ("Office", str(r["regional_office"])), ("Engaged", fmt(r["engage_date"])),
            ("Closed", fmt(r["close_date"])),
            ("Close value", money(r["close_value"]) if r["is_closed"] else "-"),
            ("Sales cycle", f"{r['sales_cycle_days']:.0f} days" if r["is_closed"] else "-"),
            ("Days open", f"{r['open_age_days']:.0f}" if pd.notna(r["open_age_days"]) else "-"),
            ("Win probability", f"{r['win_probability']:.2f}" if pd.notna(r["win_probability"]) else "-"),
            ("Source", str(r["source"])),
        ])
