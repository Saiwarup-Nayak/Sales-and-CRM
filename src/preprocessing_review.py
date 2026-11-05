"""Review-oriented view of every preprocessing step.

Each function compares the raw GitHub tables with the cleaned/joined output of
``src.preprocessing`` and returns tables that explain *what* changed, *how
much* changed, and *why* - for display in the data-review UI.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.preprocessing import NOT_ASSIGNED, PreparedData

NUMERIC_COLUMNS = {
    "sales_price": "Product list price (USD)",
    "close_value": "Won deal value (USD)",
    "revenue": "Account annual revenue (USD M)",
    "employees": "Account employees",
    "year_established": "Account year established",
    "sales_cycle_days": "Sales cycle (days, closed deals)",
}


# ---------------------------------------------------------------------------
# 1. Raw dataset
# ---------------------------------------------------------------------------
def raw_joined(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The complete dataset exactly as published, joined on the raw keys (no fixes).

    Rows whose keys do not match (e.g. product 'GTXPro') are kept with empty
    attributes, which makes the need for cleaning visible.
    """
    return (raw["sales_pipeline"]
            .merge(raw["products"], on="product", how="left")
            .merge(raw["sales_teams"], on="sales_agent", how="left")
            .merge(raw["accounts"], on="account", how="left"))


def table_overview(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name in config.REQUIRED_COLUMNS:
        df = raw[name]
        rows.append({"table": name, "rows": len(df), "columns": df.shape[1],
                     "missing cells": int(df.isna().sum().sum()),
                     "duplicate rows": int(df.duplicated().sum()),
                     "memory (KB)": round(df.memory_usage(deep=True).sum() / 1024, 1)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. Cleaning log
# ---------------------------------------------------------------------------
def _ws_issues(s: pd.Series) -> pd.Series:
    s = s.dropna().astype(str)
    return s[(s != s.str.strip()) | s.str.contains(r"\s{2,}", regex=True)]


def cleaning_log(raw: dict[str, pd.DataFrame], prep: PreparedData) -> pd.DataFrame:
    """One row per cleaning rule: technique, rows affected, and a before -> after example."""
    sp, ac = raw["sales_pipeline"], raw["accounts"]
    log = []

    def add(step, table, column, technique, n, before="-", after="-", reason=""):
        log.append({"step": step, "table": table, "column": column, "technique": technique,
                    "rows affected": int(n), "example before": str(before), "example after": str(after),
                    "why": reason})

    ws_total = sum(len(_ws_issues(raw[t][c])) for t in config.REQUIRED_COLUMNS
                   for c in raw[t].select_dtypes(include="object").columns)
    add("Whitespace trimming", "all tables", "all text columns", "strip + collapse repeated spaces", ws_total,
        reason="Hidden spaces break joins and group-bys. Checked even if none are present.")

    for wrong, right in config.PRODUCT_NAME_FIXES.items():
        add("Category standardisation", "sales_pipeline", "product", "map to master product list",
            (sp["product"] == wrong).sum(), wrong, right,
            "Pipeline spells the product differently from products.csv; without the fix these deals lose "
            "their price and series in the join.")
    for wrong, right in config.SECTOR_NAME_FIXES.items():
        add("Typo correction", "accounts", "sector", "lower-case + spelling fix",
            (ac["sector"].str.lower() == wrong).sum(), wrong, right, "Misspelled sector label.")

    stage_bad = sp["deal_stage"].notna() & (sp["deal_stage"] != sp["deal_stage"].str.title())
    add("Case normalisation", "sales_pipeline", "deal_stage", "Title Case", stage_bad.sum(),
        reason="Ensures 'won'/'WON' are counted as 'Won'.")
    invalid_stage = ~sp["deal_stage"].str.title().isin(config.VALID_STAGES)
    add("Domain validation", "sales_pipeline", "deal_stage", f"must be one of {config.VALID_STAGES}",
        invalid_stage.sum(), reason="Unknown stages are removed.")

    for c in ["engage_date", "close_date"]:
        parsed = pd.to_datetime(sp[c], errors="coerce")
        add("Type conversion", "sales_pipeline", c, "text -> datetime", sp[c].notna().sum(),
            sp[c].dropna().iloc[0], f"{parsed.dropna().iloc[0]!r}", "Enables date filters, cycle length, monthly trends.")
        add("Invalid date check", "sales_pipeline", c, "unparseable -> missing",
            (sp[c].notna() & parsed.isna()).sum())

    add("Duplicate removal", "sales_pipeline", "all columns", "drop exact duplicate rows", sp.duplicated().sum())
    add("Duplicate removal", "sales_pipeline", "opportunity_id", "keep first per ID",
        sp["opportunity_id"].duplicated().sum(), reason="One row per opportunity is required.")
    add("Duplicate removal", "accounts", "account", "keep first per account", ac["account"].duplicated().sum())
    add("Range check", "sales_pipeline", "close_value", "negative -> missing", (sp["close_value"] < 0).sum())
    add("Range check", "accounts", "revenue / employees", "negative values flagged",
        ((ac["revenue"] < 0) | (ac["employees"] < 0)).sum())

    open_mask = sp["deal_stage"].isin(config.OPEN_STAGES)
    add("Missing-value handling", "sales_pipeline", "account", f"fill '{NOT_ASSIGNED}' + flag account_known",
        sp["account"].isna().sum(), "NaN", NOT_ASSIGNED,
        "All of them are open deals: the account hasn't been recorded yet. The rows are kept and flagged.")
    add("Business rule", "sales_pipeline", "close_value", "open deals keep NaN (not 0)",
        (open_mask & sp["close_value"].isna()).sum(), "NaN", "NaN",
        "An open deal has no realised revenue. Filling 0 would understate deal size; filling a value would "
        "fake revenue. Estimated open value comes from list price instead (est_open_value).")
    return pd.DataFrame(log)


def dtype_changes(raw_join: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in raw_join.columns:
        if c in master.columns:
            rows.append({"column": c, "raw dtype": str(raw_join[c].dtype), "clean dtype": str(master[c].dtype),
                         "changed": str(raw_join[c].dtype) != str(master[c].dtype)})
    return pd.DataFrame(rows)


def integrity_checks(prep: PreparedData) -> pd.DataFrame:
    return pd.DataFrame([{"check": c.name, "status": c.status, "rows": c.count, "detail": c.detail}
                         for c in prep.checks])


# ---------------------------------------------------------------------------
# 3. Missing values
# ---------------------------------------------------------------------------
MISSING_TREATMENT = {
    "account": ("Structural: open deals not yet linked to an account", f"Filled '{NOT_ASSIGNED}' + account_known flag"),
    "engage_date": ("Structural: Prospecting deals have not been engaged yet", "Kept missing (meaningful)"),
    "close_date": ("Structural: open deals have not closed", "Kept missing; is_open flag added"),
    "close_value": ("Structural: open deals have no realised value", "Kept missing; est_open_value from list price"),
    "subsidiary_of": ("Not applicable: account is independent", "Kept missing; is_subsidiary derived for modelling"),
    "sector": ("Inherited from missing account", f"Filled '{NOT_ASSIGNED}'"),
    "year_established": ("Inherited from missing account", "Kept missing; median-imputed only inside the model"),
    "revenue": ("Inherited from missing account", "Kept missing; median-imputed only inside the model"),
    "employees": ("Inherited from missing account", "Kept missing; median-imputed only inside the model"),
    "office_location": ("Inherited from missing account", "Kept missing; separate 'missing' category in the model"),
    "series": ("Product key mismatch ('GTXPro')", "Fixed by product-name standardisation"),
    "sales_price": ("Product key mismatch ('GTXPro')", "Fixed by product-name standardisation"),
}


def missing_report(raw_join: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in raw_join.columns if c in master.columns]
    out = pd.DataFrame({
        "column": cols,
        "missing (raw)": [int(raw_join[c].isna().sum()) for c in cols],
        "missing (clean)": [int(master[c].isna().sum()) for c in cols],
    })
    out["% raw"] = out["missing (raw)"] / len(raw_join) * 100
    out["% clean"] = out["missing (clean)"] / len(master) * 100
    out["cause"] = out["column"].map(lambda c: MISSING_TREATMENT.get(c, ("-", "-"))[0])
    out["treatment"] = out["column"].map(lambda c: MISSING_TREATMENT.get(c, ("-", "No missing values"))[1])
    return out.sort_values("missing (raw)", ascending=False).reset_index(drop=True)


def missing_by_stage(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Missingness per deal stage - shows the missing values are structural, not random."""
    sp = raw["sales_pipeline"]
    cols = ["account", "engage_date", "close_date", "close_value"]
    g = sp[cols].isna().groupby(sp["deal_stage"]).mean() * 100
    g.insert(0, "deals", sp["deal_stage"].value_counts())
    return g.reindex(config.VALID_STAGES).reset_index()


# ---------------------------------------------------------------------------
# 4. Normalisation / scaling
# ---------------------------------------------------------------------------
SCALERS = {
    "Min-Max (0-1)": "x' = (x - min) / (max - min)",
    "Z-score (standardisation)": "x' = (x - mean) / std",
    "Robust (median / IQR)": "x' = (x - median) / IQR",
    "Log transform (log1p)": "x' = ln(1 + x)",
    "Decimal scaling": "x' = x / 10^k, k = digits of max|x|",
}


def scale(s: pd.Series, method: str) -> pd.Series:
    s = s.astype(float)
    if method.startswith("Min-Max"):
        rng = s.max() - s.min()
        return (s - s.min()) / rng if rng else s * 0
    if method.startswith("Z-score"):
        sd = s.std(ddof=0)
        return (s - s.mean()) / sd if sd else s * 0
    if method.startswith("Robust"):
        iqr = s.quantile(0.75) - s.quantile(0.25)
        return (s - s.median()) / iqr if iqr else s * 0
    if method.startswith("Log"):
        return np.log1p(s.clip(lower=0))
    if method.startswith("Decimal"):
        k = int(np.ceil(np.log10(s.abs().max() + 1)))
        return s / 10**k
    raise ValueError(method)


def numeric_source(master: pd.DataFrame, column: str) -> pd.Series:
    """Values to scale: close_value uses won deals only; account attributes de-duplicated per account."""
    if column == "close_value":
        return master.loc[master["is_won"], "close_value"].dropna()
    if column in ("revenue", "employees", "year_established"):
        return master.loc[master["account_known"]].drop_duplicates("account")[column].dropna()
    if column == "sales_price":
        return master.drop_duplicates("product")[column].dropna()
    return master[column].dropna()


def describe_before_after(s: pd.Series, method: str) -> pd.DataFrame:
    after = scale(s, method)
    stats = lambda x: {"count": len(x), "mean": x.mean(), "std": x.std(ddof=0), "min": x.min(),
                       "median": x.median(), "max": x.max(), "skewness": x.skew()}
    return pd.DataFrame({"before": stats(s), "after": stats(after)})


# ---------------------------------------------------------------------------
# 5. Outliers
# ---------------------------------------------------------------------------
def outlier_report(master: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col, label in NUMERIC_COLUMNS.items():
        s = numeric_source(master, col)
        if s.empty:
            continue
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        z = (s - s.mean()) / s.std(ddof=0) if s.std(ddof=0) else s * 0
        rows.append({"column": col, "description": label, "values": len(s),
                     "IQR lower fence": lo, "IQR upper fence": hi,
                     "IQR outliers": int(((s < lo) | (s > hi)).sum()),
                     "|z| > 3 outliers": int((z.abs() > 3).sum()),
                     "treatment": "Kept (flagged): genuine large deals / large accounts, not entry errors"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 6. Encoding
# ---------------------------------------------------------------------------
ENCODING_COLUMNS = ["product", "series", "sector", "regional_office", "manager", "sales_agent", "deal_stage",
                    "office_location"]


def encoding_summary(master: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in ENCODING_COLUMNS:
        k = master[c].nunique(dropna=True)
        method = ("Ordinal (stage order)" if c == "deal_stage"
                  else "One-hot" if k <= 12 else "One-hot (rare levels < 10 grouped)")
        rows.append({"column": c, "distinct values": k, "encoding used": method,
                     "one-hot columns produced": k})
    return pd.DataFrame(rows)


STAGE_ORDER = {"Prospecting": 0, "Engaging": 1, "Lost": 2, "Won": 2}


def encode_examples(master: pd.DataFrame, n: int = 8) -> dict[str, pd.DataFrame]:
    sample = master[["opportunity_id", "product", "regional_office", "deal_stage", "account"]].head(n)
    onehot = pd.concat([sample[["opportunity_id", "regional_office"]],
                        pd.get_dummies(sample["regional_office"], prefix="office", dtype=int)], axis=1)
    label_map = {p: i for i, p in enumerate(sorted(master["product"].unique()))}
    label = sample[["opportunity_id", "product"]].assign(product_label=sample["product"].map(label_map))
    ordinal = sample[["opportunity_id", "deal_stage"]].assign(stage_ordinal=sample["deal_stage"].map(STAGE_ORDER))
    freq = master["account"].value_counts(normalize=True)
    frequency = sample[["opportunity_id", "account"]].assign(account_frequency=sample["account"].map(freq).round(4))
    return {"One-hot encoding (regional_office)": onehot, "Label encoding (product)": label,
            "Ordinal encoding (deal_stage)": ordinal, "Frequency encoding (account)": frequency}


# ---------------------------------------------------------------------------
# 7. Feature engineering
# ---------------------------------------------------------------------------
ENGINEERED = [
    ("is_won / is_lost / is_closed / is_open", "flags from deal_stage", "Outcome flags for KPIs and the model target"),
    ("outcome", "Won / Lost / Open", "Simplified 3-level outcome"),
    ("won_revenue", "close_value if Won else 0", "Realised revenue only (never open deals)"),
    ("est_open_value", "sales_price if open", "Estimated value of open pipeline (won deals close at ~1.0x list price)"),
    ("sales_cycle_days", "close_date - engage_date", "Sales cycle length for closed deals"),
    ("open_age_days", "snapshot_date - engage_date", "How long an open deal has been engaged"),
    ("close_month / close_quarter", "period of close_date", "Time aggregation for trends and forecasting"),
    ("engage_month", "period of engage_date", "Cohort analysis"),
    ("account_known", "account is not missing", "Flag for deals without an account"),
]


def engineered_features(master: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, formula, purpose in ENGINEERED:
        first = name.split(" / ")[0]
        s = master[first]
        rows.append({"feature": name, "formula": formula, "purpose": purpose,
                     "non-missing": int(s.notna().sum()),
                     "example": str(s.dropna().iloc[0]) if s.notna().any() else "-"})
    return pd.DataFrame(rows)


def binning_examples(master: pd.DataFrame) -> dict[str, pd.DataFrame]:
    closed = master[master["is_closed"]].copy()
    closed["cycle_band"] = pd.cut(closed["sales_cycle_days"], [-1, 7, 30, 60, 90, np.inf],
                                  labels=["0-7 d", "8-30 d", "31-60 d", "61-90 d", "90+ d"])
    acc = master[master["account_known"]].drop_duplicates("account").copy()
    acc["employee_band"] = pd.cut(acc["employees"], [0, 1000, 5000, np.inf], labels=["< 1k", "1k-5k", "5k+"])
    acc["revenue_quartile"] = pd.qcut(acc["revenue"], 4, labels=["Q1 (smallest)", "Q2", "Q3", "Q4 (largest)"])
    return {
        "Sales cycle bands (equal-meaning bins, closed deals)":
            closed["cycle_band"].value_counts(sort=False).rename_axis("band").reset_index(name="deals"),
        "Employee bands (fixed thresholds, accounts)":
            acc["employee_band"].value_counts(sort=False).rename_axis("band").reset_index(name="accounts"),
        "Revenue quartiles (equal-frequency bins, accounts)":
            acc["revenue_quartile"].value_counts(sort=False).rename_axis("band").reset_index(name="accounts"),
    }
