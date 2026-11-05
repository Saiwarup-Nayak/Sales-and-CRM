"""Cleaning, validation and joining of the CRM Sales Opportunities tables.

The output is a single opportunity-level ``master`` table (one row per
``opportunity_id``) joined to account, product and sales-team attributes, plus
a list of data-integrity check results and a dataset profile.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src import config

NOT_ASSIGNED = "(Not assigned)"


@dataclass
class Check:
    name: str
    status: str  # "pass" | "warn" | "fail"
    detail: str
    count: int = 0


@dataclass
class PreparedData:
    master: pd.DataFrame
    tables: dict[str, pd.DataFrame]
    checks: list[Check] = field(default_factory=list)
    profile: pd.DataFrame | None = None
    snapshot_date: pd.Timestamp | None = None

    @property
    def has_failures(self) -> bool:
        return any(c.status == "fail" for c in self.checks)


class DataValidationError(ValueError):
    """Raised when the data is unusable (missing columns, empty tables)."""


# ---------------------------------------------------------------------------
# Structural validation (run on raw tables, before cleaning)
# ---------------------------------------------------------------------------
def check_required_columns(tables: dict[str, pd.DataFrame]) -> list[Check]:
    checks = []
    for tname, cols in config.REQUIRED_COLUMNS.items():
        if tname not in tables:
            checks.append(Check(f"{tname}: table present", "fail", f"Table '{tname}' is missing."))
            continue
        df = tables[tname]
        missing = [c for c in cols if c not in df.columns]
        if missing:
            checks.append(Check(f"{tname}: required columns", "fail",
                                f"Missing columns: {', '.join(missing)}", len(missing)))
        else:
            checks.append(Check(f"{tname}: required columns", "pass", f"All {len(cols)} columns present."))
        if df.empty:
            checks.append(Check(f"{tname}: non-empty", "fail", "Table has no rows."))
    return checks


def _clean_strings(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.select_dtypes(include=["object", "string"]).columns:
        s = df[col].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
        s = s.mask(s == "")
        df[col] = s.astype(object).where(s.notna(), np.nan)
    return df


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
def clean_tables(raw: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], list[Check]]:
    """Standardise types and category labels; return cleaned tables + checks."""
    checks: list[Check] = []
    t = {k: _clean_strings(v) for k, v in raw.items() if k in config.REQUIRED_COLUMNS}

    # --- products -----------------------------------------------------------
    pr = t["products"]
    pr["sales_price"] = pd.to_numeric(pr["sales_price"], errors="coerce")
    pr = pr.drop_duplicates(subset="product", keep="first")
    t["products"] = pr

    # --- accounts -----------------------------------------------------------
    ac = t["accounts"]
    before = ac["sector"].copy()
    ac["sector"] = ac["sector"].str.lower().replace(config.SECTOR_NAME_FIXES)
    n_fixed = int((before.str.lower() != ac["sector"]).sum())
    checks.append(Check("accounts: sector labels standardised",
                        "warn" if n_fixed else "pass",
                        f"{n_fixed} rows corrected (e.g. 'technolgy' -> 'technology')." if n_fixed
                        else "No inconsistent sector labels.", n_fixed))
    for c in ["year_established", "revenue", "employees"]:
        ac[c] = pd.to_numeric(ac[c], errors="coerce")
    dup_acc = int(ac["account"].duplicated().sum())
    checks.append(Check("accounts: unique account names", "warn" if dup_acc else "pass",
                        f"{dup_acc} duplicate account names (first kept)." if dup_acc
                        else "Account names are unique.", dup_acc))
    ac = ac.drop_duplicates(subset="account", keep="first")
    implausible = int(((ac["revenue"] < 0) | (ac["employees"] < 0)).sum())
    checks.append(Check("accounts: plausible revenue/employees", "warn" if implausible else "pass",
                        f"{implausible} accounts with negative revenue/employees." if implausible
                        else "No negative account revenue or headcount.", implausible))
    t["accounts"] = ac

    # --- sales teams --------------------------------------------------------
    st = t["sales_teams"].drop_duplicates(subset="sales_agent", keep="first")
    t["sales_teams"] = st

    # --- pipeline -----------------------------------------------------------
    sp = t["sales_pipeline"]
    n_exact_dup = int(sp.duplicated().sum())
    sp = sp.drop_duplicates()
    dup_ids = int(sp["opportunity_id"].duplicated().sum())
    checks.append(Check("pipeline: duplicate opportunity IDs", "warn" if (dup_ids or n_exact_dup) else "pass",
                        f"{n_exact_dup} exact duplicate rows removed; {dup_ids} conflicting duplicate IDs (first kept)."
                        if (dup_ids or n_exact_dup) else "All opportunity IDs are unique.", dup_ids + n_exact_dup))
    sp = sp.drop_duplicates(subset="opportunity_id", keep="first")

    before = sp["product"].copy()
    sp["product"] = sp["product"].replace(config.PRODUCT_NAME_FIXES)
    n_prod = int((before != sp["product"]).sum())
    checks.append(Check("pipeline: product names match product table", "warn" if n_prod else "pass",
                        f"{n_prod} rows renamed using {config.PRODUCT_NAME_FIXES}." if n_prod
                        else "Product names already consistent.", n_prod))

    sp["deal_stage"] = sp["deal_stage"].str.title()
    bad_stage = ~sp["deal_stage"].isin(config.VALID_STAGES)
    checks.append(Check("pipeline: valid deal stages", "fail" if bad_stage.any() else "pass",
                        f"{int(bad_stage.sum())} rows with unknown stage removed." if bad_stage.any()
                        else f"All stages in {config.VALID_STAGES}.", int(bad_stage.sum())))
    sp = sp[~bad_stage]

    for c in ["engage_date", "close_date"]:
        raw_notna = sp[c].notna()
        sp[c] = pd.to_datetime(sp[c], errors="coerce")
        invalid = int((raw_notna & sp[c].isna()).sum())
        checks.append(Check(f"pipeline: valid {c}", "warn" if invalid else "pass",
                            f"{invalid} unparseable dates set to missing." if invalid
                            else "All non-empty dates parse.", invalid))

    sp["close_value"] = pd.to_numeric(sp["close_value"], errors="coerce")
    neg = sp["close_value"] < 0
    checks.append(Check("pipeline: non-negative close values", "warn" if neg.any() else "pass",
                        f"{int(neg.sum())} negative values set to missing." if neg.any()
                        else "No negative close values.", int(neg.sum())))
    sp.loc[neg, "close_value"] = np.nan

    # Outcome consistency rules derived from the data dictionary.
    closed = sp["deal_stage"].isin(config.CLOSED_STAGES)
    won = sp["deal_stage"].eq("Won")
    rules = {
        "closed deals have a close date": closed & sp["close_date"].isna(),
        "open deals have no close date/value": ~closed & (sp["close_date"].notna() | sp["close_value"].notna()),
        "won deals have positive close value": won & ~(sp["close_value"] > 0),
        "lost deals have zero close value": sp["deal_stage"].eq("Lost") & sp["close_value"].fillna(0).ne(0),
        "engage date not after close date": sp["engage_date"] > sp["close_date"],
        "non-prospecting deals have an engage date": sp["deal_stage"].ne("Prospecting") & sp["engage_date"].isna(),
    }
    for rname, mask in rules.items():
        n = int(mask.sum())
        checks.append(Check(f"pipeline: {rname}", "warn" if n else "pass",
                            f"{n} rows violate this rule." if n else "Rule holds for all rows.", n))

    n_no_acc = int(sp["account"].isna().sum())
    n_no_acc_closed = int((sp["account"].isna() & closed).sum())
    checks.append(Check("pipeline: account assigned", "warn" if n_no_acc else "pass",
                        f"{n_no_acc} opportunities have no account ({n_no_acc_closed} of them closed). "
                        "Account attributes are unavailable for these deals." if n_no_acc
                        else "Every opportunity has an account.", n_no_acc))
    t["sales_pipeline"] = sp
    return t, checks


# ---------------------------------------------------------------------------
# Joining
# ---------------------------------------------------------------------------
def build_master(t: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, list[Check]]:
    """Join pipeline to products, sales teams and accounts (many-to-one)."""
    checks: list[Check] = []
    sp = t["sales_pipeline"]

    for key, tname in [("product", "products"), ("sales_agent", "sales_teams"), ("account", "accounts")]:
        keys = sp[key].dropna()
        unmatched = keys[~keys.isin(t[tname][key])]
        checks.append(Check(f"join: pipeline.{key} -> {tname}", "fail" if len(unmatched) else "pass",
                            f"{len(unmatched)} rows ({unmatched.nunique()} distinct values) have no match: "
                            f"{sorted(unmatched.unique())[:5]}" if len(unmatched)
                            else "All keys match.", len(unmatched)))

    m = (sp.merge(t["products"], on="product", how="left", validate="many_to_one")
           .merge(t["sales_teams"], on="sales_agent", how="left", validate="many_to_one")
           .merge(t["accounts"], on="account", how="left", validate="many_to_one"))
    if len(m) != len(sp):
        raise DataValidationError("Join changed the number of opportunity rows - inconsistent keys.")
    checks.append(Check("join: row count preserved", "pass", f"{len(m):,} opportunities after joins."))

    inactive = sorted(set(t["sales_teams"]["sales_agent"]) - set(sp["sales_agent"]))
    checks.append(Check("sales_teams: agents with opportunities", "warn" if inactive else "pass",
                        f"{len(inactive)} agents have no opportunities: {', '.join(inactive)}." if inactive
                        else "Every agent has at least one opportunity.", len(inactive)))
    return add_derived_columns(m), checks


def add_derived_columns(m: pd.DataFrame) -> pd.DataFrame:
    m = m.copy()
    m["account_known"] = m["account"].notna()
    m["account"] = m["account"].fillna(NOT_ASSIGNED)
    m["sector"] = m["sector"].fillna(NOT_ASSIGNED)
    m["is_won"] = m["deal_stage"].eq("Won")
    m["is_lost"] = m["deal_stage"].eq("Lost")
    m["is_closed"] = m["is_won"] | m["is_lost"]
    m["is_open"] = ~m["is_closed"]
    # Realised revenue only comes from won deals.
    m["won_revenue"] = np.where(m["is_won"], m["close_value"].fillna(0), 0.0)
    # Estimated value of open deals = product list price (won deals close at ~1.0x list price).
    m["est_open_value"] = np.where(m["is_open"], m["sales_price"], np.nan)
    m["sales_cycle_days"] = np.where(m["is_closed"], (m["close_date"] - m["engage_date"]).dt.days, np.nan)
    m["close_month"] = m["close_date"].dt.to_period("M").dt.to_timestamp()
    m["close_quarter"] = m["close_date"].dt.to_period("Q").astype("string")
    m["engage_month"] = m["engage_date"].dt.to_period("M").dt.to_timestamp()
    snapshot = max(m["close_date"].max(), m["engage_date"].max())
    m["open_age_days"] = np.where(m["is_open"], (snapshot - m["engage_date"]).dt.days, np.nan)
    m["outcome"] = np.select([m["is_won"], m["is_lost"]], ["Won", "Lost"], "Open")
    m.attrs["snapshot_date"] = snapshot
    return m


# ---------------------------------------------------------------------------
# Profiling & storage
# ---------------------------------------------------------------------------
def profile_tables(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, df in tables.items():
        date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
        ranges = "; ".join(f"{c}: {df[c].min():%Y-%m-%d} to {df[c].max():%Y-%m-%d}"
                           for c in date_cols if df[c].notna().any())
        rows.append({
            "table": name, "rows": len(df), "columns": df.shape[1],
            "missing_cells": int(df.isna().sum().sum()),
            "columns_with_missing": ", ".join(f"{c} ({n})" for c, n in df.isna().sum().items() if n) or "-",
            "date_ranges": ranges or "-",
        })
    return pd.DataFrame(rows)


def write_sqlite(master: pd.DataFrame, tables: dict[str, pd.DataFrame], path: Path = config.SQLITE_PATH) -> Path:
    """Persist cleaned tables + master to SQLite for SQL access."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        for name, df in {**tables, "opportunities": master}.items():
            out = df.copy()
            for c in out.columns:
                if pd.api.types.is_datetime64_any_dtype(out[c]):
                    out[c] = out[c].dt.strftime("%Y-%m-%d")
            out.to_sql(name, con, if_exists="replace", index=False)
    return path


def prepare(raw: dict[str, pd.DataFrame], write_db: bool = True) -> PreparedData:
    """Full pipeline: structural checks -> clean -> join -> derive -> profile -> SQLite."""
    checks = check_required_columns(raw)
    if any(c.status == "fail" for c in checks):
        failed = "; ".join(f"{c.name}: {c.detail}" for c in checks if c.status == "fail")
        raise DataValidationError(f"Source data is not usable: {failed}")
    cleaned, c2 = clean_tables(raw)
    master, c3 = build_master(cleaned)
    if master.empty:
        raise DataValidationError("No opportunities remain after cleaning.")
    profile = profile_tables({**{k: raw[k] for k in config.REQUIRED_COLUMNS}, "opportunities (joined)": master})
    if write_db:
        write_sqlite(master, cleaned)
    snapshot = master.attrs.pop("snapshot_date")
    return PreparedData(master=master, tables=cleaned, checks=checks + c2 + c3,
                        profile=profile, snapshot_date=snapshot)
