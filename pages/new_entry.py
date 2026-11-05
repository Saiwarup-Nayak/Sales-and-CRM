"""Add / update: create opportunities and accounts, move deals through the pipeline, manage own entries."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import crm_store
from src.crm_store import ValidationError
from src.preprocessing import NOT_ASSIGNED
from src.ui import get_lookups, get_master, master_with_scores, money, page_header, stage_pill

master, snapshot = get_master()
lk = get_lookups()
page_header("Add / update", "Create new records or move a deal through the pipeline. Every entry is validated "
                            "before it is saved.")
# The sample data ends at the snapshot date; default new dates there so new records line up with the history.
DEFAULT_DATE = min(snapshot.date(), date.today())
NO_ACCOUNT = "(No account yet)"

agents = {a["sales_agent"]: a for a in lk["agents"]}
products = {p["product"]: p for p in lk["products"]}


def show_errors(exc: ValidationError) -> None:
    st.error("**Not saved.** Please fix the following:\n" + "\n".join(f"- {e}" for e in exc.errors))


def show_saved() -> None:
    msg = st.session_state.pop("saved_msg", None)
    if msg:
        st.success(msg, icon=":material/check_circle:")


tab_new, tab_update, tab_acc, tab_mine = st.tabs(
    [":material/add: New opportunity", ":material/swap_horiz: Update a deal", ":material/domain_add: New account",
     ":material/history: My entries"])

# ---------------------------------------------------------------------------
# New opportunity
# ---------------------------------------------------------------------------
with tab_new:
    show_saved() if st.session_state.get("saved_tab") == "new" else None
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        agent = c1.selectbox("Sales agent *", list(agents), index=None, placeholder="Choose a rep",
                             format_func=lambda a: f"{a} · {agents[a]['regional_office']}")
        if agent:
            c1.caption(f"Manager: {agents[agent]['manager']}")
        product = c2.selectbox("Product *", list(products), index=None, placeholder="Choose a product",
                               format_func=lambda p: f"{p} · {money(products[p]['sales_price'])}")
        if product:
            c2.caption(f"Series {products[product]['series']} · list price {money(products[product]['sales_price'])}")
        account = c3.selectbox("Account", [NO_ACCOUNT] + lk["accounts"],
                               help="Missing an account? Add it in the New account tab first.")
        stage = st.segmented_control("Stage *", ["Prospecting", "Engaging", "Won", "Lost"], default="Prospecting",
                                     key="new_stage")
        d1, d2, d3 = st.columns(3)
        engage = close = value = None
        if stage in ("Engaging", "Won", "Lost"):
            engage = d1.date_input("Engage date *", DEFAULT_DATE, max_value=date.today(), format="DD/MM/YYYY")
        else:
            d1.caption("Prospecting deals have no engage date yet.")
        if stage in ("Won", "Lost"):
            close = d2.date_input("Close date *", DEFAULT_DATE, max_value=date.today(), format="DD/MM/YYYY")
            if stage == "Won":
                default_val = float(products[product]["sales_price"]) if product else 0.0
                value = d3.number_input("Close value ($) *", min_value=0.0, value=default_val, step=50.0,
                                        help="Defaults to the product's list price. Won deals close at a median "
                                             "1.0× list price in the history.")
            else:
                d3.number_input("Close value ($)", value=0.0, disabled=True, help="Lost deals have no revenue.")
        if st.button("Create opportunity", type="primary", icon=":material/add:"):
            rec = {"sales_agent": agent, "product": product, "account": None if account == NO_ACCOUNT else account,
                   "deal_stage": stage, "engage_date": engage, "close_date": close, "close_value": value}
            try:
                oid = crm_store.add_opportunity(rec)
                st.session_state["saved_tab"] = "new"
                st.session_state["saved_msg"] = (f"Opportunity **{oid}** created ({stage}, {product}"
                                                 f"{', ' + account if account != NO_ACCOUNT else ''}).")
                st.session_state["last_created"] = oid
                st.rerun()
            except ValidationError as exc:
                show_errors(exc)

    last = st.session_state.get("last_created")
    if last:
        scored = master_with_scores()
        row = scored[scored["opportunity_id"] == last]
        if len(row) and row.iloc[0]["is_open"] and pd.notna(row.iloc[0]["win_probability"]):
            st.info(f"Model estimate for **{last}**: win probability **{row.iloc[0]['win_probability']:.2f}**. "
                    "This is only a rough guide, because the model is no better than chance on this data.")

# ---------------------------------------------------------------------------
# Update a deal
# ---------------------------------------------------------------------------
with tab_update:
    show_saved() if st.session_state.get("saved_tab") == "update" else None
    open_deals = master[master["is_open"]].sort_values(["deal_stage", "engage_date"], ascending=[True, False])
    label = {r.opportunity_id: f"{r.opportunity_id} · {r.deal_stage} · {r.product} · {r.account} · {r.sales_agent}"
             for r in open_deals.itertuples()}
    ids = list(label)
    # Pre-select a deal sent from the Opportunities page; a stable key keeps the choice across reruns.
    pre = st.session_state.pop("edit_opportunity", None)
    if pre in ids:
        st.session_state["update_oid"] = pre
    elif st.session_state.get("update_oid") not in ids:
        st.session_state.pop("update_oid", None)  # deal was closed by the last update
    with st.container(border=True):
        oid = st.selectbox("Open deal", ids, index=None, key="update_oid",
                           placeholder=f"Search {len(ids):,} open deals by ID, product, account or rep",
                           format_func=label.get)
        if oid:
            cur = open_deals[open_deals["opportunity_id"] == oid].iloc[0]
            st.markdown(f"Current stage {stage_pill(cur['deal_stage'])} · {cur['product']} "
                        f"({money(cur['sales_price'])}) · {cur['account']} · {cur['sales_agent']}",
                        unsafe_allow_html=True)
            options = ["Engaging", "Won", "Lost"] if cur["deal_stage"] == "Prospecting" else ["Won", "Lost"]
            new_stage = st.segmented_control("Move to", options, default=options[0], key=f"upd_stage_{oid}")
            changes = {"deal_stage": new_stage}
            u1, u2, u3, u4 = st.columns(4)
            if cur["deal_stage"] == "Prospecting":
                changes["engage_date"] = u1.date_input("Engage date *", DEFAULT_DATE, max_value=date.today(),
                                                       format="DD/MM/YYYY", key=f"upd_eng_{oid}")
            else:
                u1.caption(f"Engaged {cur['engage_date']:%d %b %Y}")
            if new_stage in ("Won", "Lost"):
                changes["close_date"] = u2.date_input("Close date *", DEFAULT_DATE, max_value=date.today(),
                                                      format="DD/MM/YYYY", key=f"upd_close_{oid}")
                if new_stage == "Won":
                    changes["close_value"] = u3.number_input("Close value ($) *", min_value=0.0,
                                                             value=float(cur["sales_price"]), step=50.0,
                                                             key=f"upd_val_{oid}")
                else:
                    changes["close_value"] = 0.0
                if cur["account"] == NOT_ASSIGNED:
                    acc = u4.selectbox("Account *", lk["accounts"], index=None, key=f"upd_acc_{oid}",
                                       help="Closed deals must be linked to an account.")
                    changes["account"] = acc
            if st.button("Save update", type="primary", icon=":material/save:"):
                try:
                    crm_store.update_opportunity(oid, changes)
                    st.session_state["saved_tab"] = "update"
                    st.session_state["saved_msg"] = f"Deal **{oid}** moved to **{new_stage}**."
                    st.rerun()
                except ValidationError as exc:
                    show_errors(exc)

# ---------------------------------------------------------------------------
# New account
# ---------------------------------------------------------------------------
with tab_acc:
    show_saved() if st.session_state.get("saved_tab") == "account" else None
    with st.form("new_account", clear_on_submit=True, border=True):
        a1, a2, a3 = st.columns(3)
        name = a1.text_input("Account name *", placeholder="e.g. Northwind Traders")
        sector = a2.selectbox("Sector *", lk["sectors"], index=None, accept_new_options=True,
                              placeholder="Choose or type a new sector")
        location = a3.selectbox("HQ country", lk["locations"], index=None, accept_new_options=True,
                                placeholder="Choose or type a country")
        b1, b2, b3, b4 = st.columns(4)
        year = b1.number_input("Year established", min_value=1800, max_value=date.today().year, value=2000, step=1)
        revenue = b2.number_input("Annual revenue ($M)", min_value=0.0, value=100.0, step=10.0)
        employees = b3.number_input("Employees", min_value=0, value=500, step=10)
        parent = b4.selectbox("Parent company", ["None"] + lk["accounts"])
        if st.form_submit_button("Create account", type="primary", icon=":material/domain_add:"):
            rec = {"account": name, "sector": sector or "", "office_location": location, "year_established": int(year),
                   "revenue": float(revenue), "employees": int(employees),
                   "subsidiary_of": None if parent == "None" else parent}
            try:
                created = crm_store.add_account(rec)
                st.session_state["saved_tab"] = "account"
                st.session_state["saved_msg"] = f"Account **{created}** created. You can now assign deals to it."
                st.rerun()
            except ValidationError as exc:
                show_errors(exc)

# ---------------------------------------------------------------------------
# My entries
# ---------------------------------------------------------------------------
with tab_mine:
    show_saved() if st.session_state.get("saved_tab") == "mine" else None
    mine = crm_store.user_entries()
    opps, accs = mine["opportunities"], mine["accounts"]
    st.markdown(f"**Opportunities created or updated in this app** ({len(opps)})")
    if opps.empty:
        st.caption("Nothing yet.")
    else:
        st.dataframe(opps, hide_index=True, width="stretch",
                     column_config={"close_value": st.column_config.NumberColumn(format="$%.0f")})
    st.markdown(f"**Accounts created in this app** ({len(accs)})")
    if accs.empty:
        st.caption("Nothing yet.")
    else:
        st.dataframe(accs, hide_index=True, width="stretch")

    deletable = opps[opps["source"] == "user"]["opportunity_id"].tolist() if len(opps) else []
    if deletable or len(accs):
        with st.expander("Delete an entry you created", icon=":material/delete:"):
            kind = st.radio("Type", ["Opportunity", "Account"], horizontal=True)
            choices = deletable if kind == "Opportunity" else accs["account"].tolist()
            target = st.selectbox("Entry", choices, index=None)
            sure = st.checkbox("I understand this cannot be undone")
            if st.button("Delete", disabled=not (target and sure)):
                try:
                    (crm_store.delete_user_opportunity if kind == "Opportunity" else crm_store.delete_user_account)(target)
                    st.session_state["saved_tab"] = "mine"
                    st.session_state["saved_msg"] = f"{kind} **{target}** deleted."
                    st.rerun()
                except ValidationError as exc:
                    show_errors(exc)

    with st.expander("Reset CRM to the original GitHub data", icon=":material/restart_alt:"):
        st.warning("This re-downloads the dataset and **removes every entry and update made in this app**.")
        confirm = st.text_input("Type RESET to confirm")
        if st.button("Reset CRM", disabled=confirm != "RESET"):
            crm_store.seed_from_github(refresh=True)
            st.session_state["saved_tab"] = "mine"
            st.session_state["saved_msg"] = "CRM reset to the original dataset."
            st.rerun()
