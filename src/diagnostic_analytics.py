"""Diagnostic analytics: which factors are *associated* with won vs lost deals.

Every comparison is made on closed opportunities only (open deals have no
outcome yet). Associations are tested with a chi-square test of independence
and summarised with Cramer's V. These are observational associations: they do
not establish that a factor *causes* a deal to be won or lost.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from src.descriptive_analytics import summarise_by

DIMENSIONS = {
    "product": "Product",
    "series": "Product series",
    "price_band": "List-price band",
    "sector": "Customer sector",
    "sales_agent": "Sales representative",
    "manager": "Sales manager",
    "regional_office": "Regional office",
    "office_location": "Account HQ country",
    "employee_band": "Account size (employees)",
    "revenue_band": "Account revenue band",
    "account_age_band": "Account age",
    "engage_quarter": "Engage quarter",
}

MIN_CLOSED_PER_GROUP = 30


@dataclass
class Association:
    dimension: str
    label: str
    groups: int
    chi2: float
    p_value: float
    cramers_v: float
    spread_pp: float
    best_group: str
    best_rate: float
    worst_group: str
    worst_rate: float

    @property
    def significant(self) -> bool:
        return bool(self.p_value < 0.05)


def add_bands(df: pd.DataFrame) -> pd.DataFrame:
    """Add banded versions of numeric attributes for group comparisons."""
    df = df.copy()
    df["price_band"] = pd.cut(df["sales_price"], [0, 100, 1000, 4000, np.inf],
                              labels=["< $100", "$100-1k", "$1k-4k", "> $4k"])
    df["employee_band"] = pd.cut(df["employees"], [0, 1000, 5000, np.inf],
                                 labels=["< 1k", "1k-5k", "5k+"])
    df["revenue_band"] = pd.cut(df["revenue"], [0, 500, 2000, np.inf],
                                labels=["< $500M", "$500M-2B", "$2B+"])
    age = df["engage_date"].dt.year - df["year_established"]
    df["account_age_band"] = pd.cut(age, [-np.inf, 15, 30, np.inf], labels=["< 15 yrs", "15-30 yrs", "30+ yrs"])
    df["engage_quarter"] = df["engage_date"].dt.to_period("Q").astype("string")
    for c in ["price_band", "employee_band", "revenue_band", "account_age_band"]:
        df[c] = df[c].astype("string")
    return df


def cramers_v(table: np.ndarray) -> float:
    chi2 = stats.chi2_contingency(table, correction=False)[0]
    n = table.sum()
    k = min(table.shape) - 1
    return float(np.sqrt(chi2 / (n * k))) if n and k else np.nan


def win_rate_by(df: pd.DataFrame, dim: str) -> pd.DataFrame:
    """Win rate per group with 95% CI and a flag for groups whose CI excludes the overall rate."""
    closed = add_bands(df)
    closed = closed[closed["is_closed"] & closed[dim].notna()]
    if closed.empty:
        return pd.DataFrame()
    out = summarise_by(closed, dim)
    overall = closed["is_won"].mean()
    out["closed"] = out["won"] + out["lost"]
    out["vs_overall_pp"] = (out["win_rate"] - overall) * 100
    out["significant_vs_overall"] = (out["win_rate_lo"] > overall) | (out["win_rate_hi"] < overall)
    out["low_volume"] = out["closed"] < MIN_CLOSED_PER_GROUP
    return out.sort_values("win_rate", ascending=False).reset_index(drop=True)


def test_association(df: pd.DataFrame, dim: str) -> Association | None:
    closed = add_bands(df)
    closed = closed[closed["is_closed"] & closed[dim].notna()]
    tab = pd.crosstab(closed[dim], closed["is_won"])
    if tab.shape[0] < 2 or tab.shape[1] < 2:
        return None
    chi2, p, _, _ = stats.chi2_contingency(tab.values, correction=False)
    rates = win_rate_by(df, dim)
    rates = rates[~rates["low_volume"]] if (~rates["low_volume"]).sum() >= 2 else rates
    best, worst = rates.iloc[0], rates.iloc[-1]
    return Association(dim, DIMENSIONS.get(dim, dim), int(tab.shape[0]), float(chi2), float(p),
                       cramers_v(tab.values), float((best["win_rate"] - worst["win_rate"]) * 100),
                       str(best[dim]), float(best["win_rate"]), str(worst[dim]), float(worst["win_rate"]))


def association_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Rank all candidate dimensions by strength of association with outcome."""
    rows = []
    for dim in DIMENSIONS:
        a = test_association(df, dim)
        if a is not None:
            rows.append({**a.__dict__, "significant": a.significant})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("cramers_v", ascending=False).reset_index(drop=True)


CYCLE_BINS = [-1, 7, 30, 60, 90, np.inf]
CYCLE_LABELS = ["0-7 days", "8-30 days", "31-60 days", "61-90 days", "90+ days"]


def cycle_vs_outcome(df: pd.DataFrame) -> dict:
    """Compare sales-cycle duration for won vs lost deals.

    Cycle length is only known once a deal closes, so this is a descriptive
    pattern and is NOT used as a model feature (it would leak the outcome).
    """
    closed = df[df["is_closed"] & df["sales_cycle_days"].notna()].copy()
    if closed.empty or closed["is_won"].nunique() < 2:
        return {}
    won = closed.loc[closed["is_won"], "sales_cycle_days"]
    lost = closed.loc[closed["is_lost"], "sales_cycle_days"]
    u, p = stats.mannwhitneyu(won, lost, alternative="two-sided")
    closed["cycle_band"] = pd.cut(closed["sales_cycle_days"], CYCLE_BINS, labels=CYCLE_LABELS).astype("string")
    bands = summarise_by(closed, "cycle_band")
    bands["cycle_band"] = pd.Categorical(bands["cycle_band"], CYCLE_LABELS, ordered=True)
    return {
        "won_median": float(won.median()), "lost_median": float(lost.median()),
        "won_mean": float(won.mean()), "lost_mean": float(lost.mean()),
        "mannwhitney_u": float(u), "p_value": float(p),
        "bands": bands.sort_values("cycle_band").reset_index(drop=True),
        "data": closed[["sales_cycle_days", "outcome"]],
    }


def win_rate_trend(df: pd.DataFrame, dim: str, freq: str = "Q") -> pd.DataFrame:
    """Win rate per group per close period (used to spot declining segments)."""
    closed = df[df["is_closed"]].copy()
    closed["period"] = closed["close_date"].dt.to_period(freq).astype("string")
    return summarise_by(closed, [dim, "period"]).sort_values([dim, "period"])


def generate_insights(df: pd.DataFrame) -> list[dict]:
    """Plain-language findings backed by the numbers above."""
    insights = []
    closed = df[df["is_closed"]]
    if len(closed) < 50 or closed["is_won"].nunique() < 2:
        return [{"text": "Too few closed deals in the current selection for reliable diagnostics.",
                 "evidence": f"{len(closed)} closed deals."}]
    overall = closed["is_won"].mean()
    assoc = association_summary(df)
    if not assoc.empty:
        sig = assoc[assoc["significant"]]
        weak = assoc[~assoc["significant"]]
        for _, r in sig.head(3).iterrows():
            insights.append({
                "text": f"{r['label']} shows a statistically significant association with outcome "
                        f"(win rate ranges from {r['worst_rate']:.1%} for '{r['worst_group']}' to "
                        f"{r['best_rate']:.1%} for '{r['best_group']}').",
                "evidence": f"Chi-square p = {r['p_value']:.3g}, Cramer's V = {r['cramers_v']:.3f} "
                            f"({_effect_label(r['cramers_v'])} effect).",
            })
        if len(weak):
            insights.append({
                "text": "No reliable association with outcome was found for: "
                        + ", ".join(weak["label"].head(8)) + ".",
                "evidence": "Chi-square p >= 0.05 for each; differences between groups are within what "
                            "random variation would produce.",
            })
        if assoc["cramers_v"].max() < 0.1:
            insights.append({
                "text": "Overall, no single recorded attribute strongly separates won from lost deals. "
                        "Outcomes are likely driven by factors not captured in the CRM (e.g. buyer needs, "
                        "competition, engagement quality).",
                "evidence": f"Largest Cramer's V across all dimensions = {assoc['cramers_v'].max():.3f} "
                            "(values < 0.1 are conventionally negligible).",
            })
    cyc = cycle_vs_outcome(df)
    if cyc:
        insights.append({
            "text": f"Won deals took a median {cyc['won_median']:.0f} days to close versus "
                    f"{cyc['lost_median']:.0f} days for lost deals; lost deals tend to be closed out early.",
            "evidence": f"Mann-Whitney U p = {cyc['p_value']:.3g}. Cycle length is known only after "
                        "closing, so it describes outcomes rather than predicting them.",
        })
    insights.append({"text": f"Overall win rate on closed deals is {overall:.1%}.",
                     "evidence": f"{int(closed['is_won'].sum()):,} won of {len(closed):,} closed."})
    return insights


def _effect_label(v: float) -> str:
    return "negligible" if v < 0.1 else "small" if v < 0.3 else "medium" if v < 0.5 else "large"
