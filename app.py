"""Pipeline CRM - entry point.

Run:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from src import crm_store
from src.data_loader import DataLoadError
from src.ui import ensure_store, inject_css

st.set_page_config(page_title="Pipeline CRM", page_icon=":material/hub:", layout="wide")
inject_css()

try:
    ensure_store()
except DataLoadError as exc:
    st.error(f"**The CRM database could not be created.** {exc}")
    st.stop()

with st.sidebar:
    st.markdown('<div class="brand">Pipeline CRM</div>'
                '<div class="brand-sub">Sales &amp; CRM Intelligence</div>', unsafe_allow_html=True)

pages = {
    "CRM": [
        st.Page("pages/dashboard.py", title="Dashboard", icon=":material/space_dashboard:", default=True),
        st.Page("pages/opportunities.py", title="Opportunities", icon=":material/handshake:"),
        st.Page("pages/accounts.py", title="Accounts", icon=":material/apartment:"),
        st.Page("pages/sales_team.py", title="Sales team", icon=":material/groups:"),
    ],
    "Manage": [
        st.Page("pages/new_entry.py", title="Add / update", icon=":material/add_circle:"),
    ],
    "Data": [
        st.Page("pages/data_review.py", title="Data review", icon=":material/dataset:"),
    ],
}
nav = st.navigation(pages)

with st.sidebar:
    m = crm_store.meta()
    entries = crm_store.user_entries()
    st.caption(f"Seeded from GitHub {m.get('seeded_at', '')[:10]}  \n"
               f"{len(entries['opportunities'])} deals and {len(entries['accounts'])} accounts added or updated here")

nav.run()
