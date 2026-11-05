"""Shared UI helpers for the CRM platform: theme, chart styling, cards, cached loaders."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import crm_store
from src.opportunity_model import InsufficientDataError, train_and_evaluate

# Validated reference palette (light mode)
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff"
BLUE_RAMP = ["#f0efec", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]
OUTCOME_COLORS = {"Won": BLUE, "Lost": ORANGE, "Open": "#b5b3ab"}
STAGE_COLORS = {"Prospecting": "#9ec5f4", "Engaging": "#3987e5", "Won": "#184f95", "Lost": ORANGE}

CSS = """
<style>
  :root { --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --line:rgba(11,11,11,.09); --blue:#2a78d6; }
  .block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1440px; }
  [data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid var(--line); }
  [data-testid="stSidebarNav"] span { font-weight: 500; }
  h1, h2, h3 { letter-spacing: -0.01em; }
  .page-head { display:flex; align-items:flex-end; justify-content:space-between; gap:16px;
               margin: 0 0 1.1rem 0; flex-wrap: wrap; }
  .page-head h1 { font-size: 1.75rem; margin: 0; padding: 0; color: var(--ink); }
  .page-head p { margin: .25rem 0 0 0; color: var(--ink2); font-size: .95rem; }
  .kpi-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px;
              margin-bottom: 1.1rem; }
  .kpi { background:#fff; border:1px solid var(--line); border-radius: 12px; padding: 14px 16px;
         box-shadow: 0 1px 2px rgba(11,11,11,.04); }
  .kpi .lbl { color: var(--ink2); font-size: .8rem; font-weight: 500; text-transform: uppercase;
              letter-spacing: .04em; }
  .kpi .val { color: var(--ink); font-size: 1.55rem; font-weight: 650; margin-top: 4px; line-height: 1.2; }
  .kpi .sub { color: var(--muted); font-size: .8rem; margin-top: 2px; }
  .kpi.accent { border-left: 3px solid var(--blue); }
  .brand { font-weight: 700; font-size: 1.15rem; color: var(--ink); letter-spacing: -0.01em; }
  .brand-sub { color: var(--muted); font-size: .8rem; margin-top: -2px; }
  .pill { display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem; font-weight: 600; }
  .pill.Prospecting { background:#e3eefc; color:#1c5cab; } .pill.Engaging { background:#cde2fb; color:#184f95; }
  .pill.Won { background:#184f95; color:#fff; } .pill.Lost { background:#fde3d8; color:#a3401a; }
  .detail-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px 18px; }
  .detail-grid .k { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
  .detail-grid .v { color: var(--ink); font-size: .98rem; font-weight: 500; }
  .note { color: var(--ink2); font-size: .9rem; }
  [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; }
  div[data-testid="stForm"] { border-radius: 12px; background: #fff; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="page-head"><div><h1>{html.escape(title)}</h1>'
                f'<p>{html.escape(subtitle)}</p></div></div>', unsafe_allow_html=True)


def kpi_cards(items: list[tuple[str, str, str]], accent_first: bool = True) -> None:
    """items: (label, value, sub-text)."""
    cards = "".join(
        f'<div class="kpi{" accent" if (i == 0 and accent_first) else ""}"><div class="lbl">{html.escape(l)}</div>'
        f'<div class="val">{html.escape(v)}</div><div class="sub">{html.escape(s)}</div></div>'
        for i, (l, v, s) in enumerate(items))
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def stage_pill(stage: str) -> str:
    return f'<span class="pill {html.escape(stage)}">{html.escape(stage)}</span>'


def detail_grid(pairs: list[tuple[str, str]]) -> None:
    cells = "".join(f'<div><div class="k">{html.escape(k)}</div><div class="v">{v}</div></div>' for k, v in pairs)
    st.markdown(f'<div class="detail-grid">{cells}</div>', unsafe_allow_html=True)


def money(x, decimals: int = 0) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.2f}M"
    if abs(x) >= 1e4:
        return f"${x / 1e3:,.1f}K"
    return f"${x:,.{decimals}f}"


def pct(x) -> str:
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.1%}"


def style(fig: go.Figure, height: int = 340, title: str | None = None) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=44 if title else 16, b=8),
                      title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left") if title else None,
                      plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
                      font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=INK2, size=12),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=1, xanchor="right", title=None),
                      bargap=0.28, hoverlabel=dict(bgcolor="white", font_color=INK))
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False, title_font=dict(size=12))
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False, title_font=dict(size=12))
    return fig


# ---------------------------------------------------------------------------
# Cached data access (keyed on the store version, so writes refresh everything)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading CRM data...")
def _master(version: int):
    return crm_store.load_master()


@st.cache_data(show_spinner=False)
def _lookups(version: int):
    return crm_store.lookups()


@st.cache_resource(show_spinner="Scoring open opportunities...")
def _model(version: int):
    master, _ = _master(version)
    try:
        return train_and_evaluate(master)
    except InsufficientDataError:
        return None


def ensure_store() -> None:
    if not crm_store.is_initialised():
        with st.spinner("First run: downloading the dataset from GitHub and creating the CRM database..."):
            crm_store.ensure_store()


def get_master() -> tuple[pd.DataFrame, pd.Timestamp]:
    return _master(crm_store.version())


def get_lookups() -> dict:
    return _lookups(crm_store.version())


def get_model():
    return _model(crm_store.version())


def master_with_scores() -> pd.DataFrame:
    """Master table plus win_probability for open deals (NaN for closed)."""
    master, _ = get_master()
    model = get_model()
    out = master.copy()
    out["win_probability"] = np.nan
    if model is not None and len(model.scored_open):
        prob = model.scored_open.set_index("opportunity_id")["win_probability"]
        out["win_probability"] = out["opportunity_id"].map(prob)
    return out
