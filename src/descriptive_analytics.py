"""Descriptive analytics: what happened in the sales operation.

All functions take an opportunity-level master DataFrame (optionally filtered)
and return plain DataFrames / dicts, so they are easy to test and to render.
Revenue always means *won* revenue (``won_revenue``). The value of open deals is
reported separately as an *estimate* based on product list price.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.stats_utils import safe_div, wilson_ci


def compute_kpis(df: pd.DataFrame) -> dict:
    won = df[df["is_won"]]
    closed = df[df["is_closed"]]
    open_ = df[df["is_open"]]
    return {
        "total_opportunities": int(len(df)),
        "closed_opportunities": int(len(closed)),
        "open_opportunities": int(len(open_)),
        "won_deals": int(len(won)),
        "lost_deals": int(df["is_lost"].sum()),
        "win_rate": safe_div(len(won), len(closed)),
        "won_revenue": float(won["won_revenue"].sum()),
        "avg_won_deal": float(won["won_revenue"].mean()) if len(won) else np.nan,
        "open_pipeline_est_value": float(open_["est_open_value"].sum()),
        "open_pipeline_unpriced": int(open_["est_open_value"].isna().sum()),
        "active_reps": int(df["sales_agent"].nunique()),
        "avg_sales_cycle_days": float(closed["sales_cycle_days"].mean()) if len(closed) else np.nan,
        "median_sales_cycle_days": float(closed["sales_cycle_days"].median()) if len(closed) else np.nan,
    }


def _outcome_summary(g: pd.DataFrame) -> pd.Series:
    won = int(g["is_won"].sum())
    lost = int(g["is_lost"].sum())
    return pd.Series({
        "opportunities": len(g),
        "open": int(g["is_open"].sum()),
        "won": won,
        "lost": lost,
        "win_rate": safe_div(won, won + lost),
        "won_revenue": float(g["won_revenue"].sum()),
        "avg_won_deal": float(g.loc[g["is_won"], "won_revenue"].mean()) if won else np.nan,
        "revenue_per_closed_deal": safe_div(g["won_revenue"].sum(), won + lost),
        "open_pipeline_est_value": float(g["est_open_value"].sum()),
        "avg_cycle_days": float(g["sales_cycle_days"].mean()) if (won + lost) else np.nan,
    })


def summarise_by(df: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    """Outcome + revenue summary per group, with a Wilson 95% CI on win rate."""
    if df.empty:
        return pd.DataFrame()
    cols = ["is_won", "is_lost", "is_open", "won_revenue", "est_open_value", "sales_cycle_days"]
    out = df.groupby(by, observed=True)[cols].apply(_outcome_summary).reset_index()
    closed = out["won"] + out["lost"]
    out["win_rate_lo"], out["win_rate_hi"] = wilson_ci(out["won"], closed)
    total_rev = out["won_revenue"].sum()
    out["revenue_share"] = out["won_revenue"] / total_rev if total_rev else np.nan
    return out.sort_values("won_revenue", ascending=False).reset_index(drop=True)


def rep_performance(df: pd.DataFrame) -> pd.DataFrame:
    """Per-representative scorecard.

    Besides raw revenue, it reports volume-normalised metrics (win rate with CI,
    revenue per closed deal) and the rep's win rate relative to their regional
    office, because reps handle different volumes and product mixes.
    """
    out = summarise_by(df, ["sales_agent", "manager", "regional_office"])
    if out.empty:
        return out
    office = summarise_by(df, "regional_office")[["regional_office", "win_rate"]]
    out = out.merge(office.rename(columns={"win_rate": "office_win_rate"}), on="regional_office", how="left")
    out["win_rate_vs_office_pp"] = (out["win_rate"] - out["office_win_rate"]) * 100
    out["revenue_rank"] = out["won_revenue"].rank(ascending=False, method="min").astype(int)
    out["win_rate_rank"] = out["win_rate"].rank(ascending=False, method="min")
    return out


def funnel(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Snapshot stage distribution and 'reached at least' milestone counts.

    The dataset stores only each opportunity's *current* stage, so these are not
    stage-to-stage transition rates. Milestones are inferred from dates: an
    engage_date means the deal reached Engaging; a close_date means it closed.
    Open deals are still in progress, so milestone ratios are lower bounds.
    """
    order = ["Prospecting", "Engaging", "Won", "Lost"]
    snap = (df["deal_stage"].value_counts().reindex(order, fill_value=0)
            .rename_axis("stage").reset_index(name="opportunities"))
    snap["share"] = snap["opportunities"] / max(len(df), 1)
    snap["est_value"] = [df.loc[df["deal_stage"] == s, "est_open_value"].sum() if s in ("Prospecting", "Engaging")
                         else df.loc[df["deal_stage"] == s, "won_revenue"].sum() for s in order]

    n = len(df)
    reached_engaging = int(df["engage_date"].notna().sum())
    closed = int(df["is_closed"].sum())
    won = int(df["is_won"].sum())
    milestones = pd.DataFrame({
        "milestone": ["Created", "Reached Engaging", "Closed (Won or Lost)", "Won"],
        "opportunities": [n, reached_engaging, closed, won],
    })
    milestones["pct_of_created"] = milestones["opportunities"] / max(n, 1)
    milestones["pct_of_previous"] = milestones["opportunities"] / milestones["opportunities"].shift(1)
    return {"snapshot": snap, "milestones": milestones}


def revenue_by_period(df: pd.DataFrame, freq: str = "M") -> pd.DataFrame:
    """Won revenue, deal counts and win rate per close period, with growth %."""
    closed = df[df["is_closed"]].copy()
    if closed.empty:
        return pd.DataFrame(columns=["period", "won_revenue", "won", "lost", "win_rate", "growth_pct"])
    closed["period"] = closed["close_date"].dt.to_period(freq).dt.to_timestamp()
    g = closed.groupby("period").agg(won_revenue=("won_revenue", "sum"), won=("is_won", "sum"),
                                     lost=("is_lost", "sum")).reset_index()
    full = pd.period_range(closed["close_date"].min(), closed["close_date"].max(), freq=freq).to_timestamp()
    g = g.set_index("period").reindex(full, fill_value=0).rename_axis("period").reset_index()
    g["win_rate"] = g["won"] / (g["won"] + g["lost"]).replace(0, np.nan)
    g["avg_won_deal"] = g["won_revenue"] / g["won"].replace(0, np.nan)
    g["growth_pct"] = g["won_revenue"].pct_change(fill_method=None) * 100
    return g


def pivot_metric(df: pd.DataFrame, rows: str, cols: str, metric: str = "won_revenue") -> pd.DataFrame:
    """Pivot for heatmaps. metric in {won_revenue, avg_won_deal, win_rate, opportunities}."""
    s = summarise_by(df, [rows, cols])
    if s.empty:
        return pd.DataFrame()
    return s.pivot(index=rows, columns=cols, values=metric)


def top_accounts(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    known = df[df["account_known"]]
    return summarise_by(known, ["account", "sector"]).head(n)
