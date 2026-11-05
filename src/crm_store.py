"""Persistent CRM store (SQLite) for the CRM platform.

The store is seeded once from the cleaned GitHub dataset and then holds every
entry made in the app. It is separate from ``data/crm.db`` (the analytics
snapshot that is rebuilt on each data refresh), so user entries are never lost
when the source data is reloaded.

Every write is validated with the same business rules used in preprocessing
(valid stage, dates in order, Won > 0, Lost = 0, open deals have no close).
"""
from __future__ import annotations

import random
import sqlite3
import string
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src import config
from src.preprocessing import NOT_ASSIGNED, build_master, clean_tables

STORE_PATH = config.DATA_DIR / "crm_app.db"
TABLES = ("opportunities", "accounts", "products", "sales_teams")

OPP_COLUMNS = ["opportunity_id", "sales_agent", "product", "account", "deal_stage",
               "engage_date", "close_date", "close_value", "source", "created_at"]
ACCOUNT_COLUMNS = ["account", "sector", "year_established", "revenue", "employees",
                   "office_location", "subsidiary_of", "source", "created_at"]


class ValidationError(ValueError):
    """Raised with a list of human-readable problems when an entry is rejected."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


# ---------------------------------------------------------------------------
# Connection / initialisation
# ---------------------------------------------------------------------------
def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def is_initialised(path: Path = STORE_PATH) -> bool:
    if not path.exists():
        return False
    with closing(_connect(path)) as con:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return set(TABLES) | {"meta"} <= names


def _date_str(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.strftime("%Y-%m-%d")


def init_store(tables: dict[str, pd.DataFrame], path: Path = STORE_PATH) -> None:
    """(Re)create the store from cleaned source tables. Removes all user entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    opp = tables["sales_pipeline"].copy()
    opp["engage_date"], opp["close_date"] = _date_str(opp["engage_date"]), _date_str(opp["close_date"])
    opp["source"], opp["created_at"] = "github", now
    acc = tables["accounts"].copy()
    acc["source"], acc["created_at"] = "github", now
    # Keep the version counter monotonic across resets so cached views keyed on it never go stale.
    next_version = (version(path) + 1) if is_initialised(path) else 1

    with closing(_connect(path)) as con, con:
        con.executescript("""
            DROP TABLE IF EXISTS opportunities; DROP TABLE IF EXISTS accounts;
            DROP TABLE IF EXISTS products; DROP TABLE IF EXISTS sales_teams; DROP TABLE IF EXISTS meta;
            CREATE TABLE products (product TEXT PRIMARY KEY, series TEXT, sales_price REAL);
            CREATE TABLE sales_teams (sales_agent TEXT PRIMARY KEY, manager TEXT, regional_office TEXT);
            CREATE TABLE accounts (account TEXT PRIMARY KEY, sector TEXT, year_established INTEGER,
                                   revenue REAL, employees INTEGER, office_location TEXT, subsidiary_of TEXT,
                                   source TEXT, created_at TEXT);
            CREATE TABLE opportunities (
                opportunity_id TEXT PRIMARY KEY,
                sales_agent TEXT NOT NULL REFERENCES sales_teams(sales_agent),
                product TEXT NOT NULL REFERENCES products(product),
                account TEXT REFERENCES accounts(account),
                deal_stage TEXT NOT NULL CHECK (deal_stage IN ('Prospecting','Engaging','Won','Lost')),
                engage_date TEXT, close_date TEXT, close_value REAL,
                source TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        """)
        tables["products"][["product", "series", "sales_price"]].to_sql("products", con, if_exists="append", index=False)
        tables["sales_teams"][["sales_agent", "manager", "regional_office"]].to_sql(
            "sales_teams", con, if_exists="append", index=False)
        acc[ACCOUNT_COLUMNS].to_sql("accounts", con, if_exists="append", index=False)
        opp[OPP_COLUMNS].to_sql("opportunities", con, if_exists="append", index=False)
        con.executemany("INSERT INTO meta VALUES (?, ?)",
                        [("version", str(next_version)), ("seeded_at", now), ("source", config.CRM_REPO)])


def seed_from_github(refresh: bool = False, path: Path = STORE_PATH) -> None:
    from src.data_loader import load_crm_raw  # local import: only needed for seeding
    raw, _ = load_crm_raw(refresh=refresh)
    cleaned, _ = clean_tables(raw)
    init_store(cleaned, path)


def ensure_store(path: Path = STORE_PATH) -> None:
    if not is_initialised(path):
        seed_from_github(path=path)


def version(path: Path = STORE_PATH) -> int:
    """Monotonic counter bumped on every write - used as a cache key."""
    with closing(_connect(path)) as con:
        return int(con.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])


def meta(path: Path = STORE_PATH) -> dict:
    with closing(_connect(path)) as con:
        return dict(con.execute("SELECT key, value FROM meta").fetchall())


def _bump(con: sqlite3.Connection) -> None:
    con.execute("UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key='version'")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def read_tables(path: Path = STORE_PATH) -> dict[str, pd.DataFrame]:
    with closing(_connect(path)) as con:
        t = {name: pd.read_sql(f"SELECT * FROM {name}", con) for name in TABLES}
    opp = t.pop("opportunities")
    for c in ("engage_date", "close_date"):
        opp[c] = pd.to_datetime(opp[c], errors="coerce")
    t["sales_pipeline"] = opp
    return t


def load_master(path: Path = STORE_PATH) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Joined opportunity-level table with derived columns (same as the analytics pipeline)."""
    t = read_tables(path)
    t["accounts"] = t["accounts"].drop(columns=["source", "created_at"])
    sources = t["sales_pipeline"][["opportunity_id", "source", "created_at", "updated_at"]]
    t["sales_pipeline"] = t["sales_pipeline"].drop(columns=["source", "created_at", "updated_at"])
    master, _ = build_master(t)
    snapshot = master.attrs.pop("snapshot_date")
    master = master.merge(sources, on="opportunity_id", how="left")
    return master, snapshot


def lookups(path: Path = STORE_PATH) -> dict[str, list]:
    t = read_tables(path)
    acc = t["accounts"]
    return {
        "agents": t["sales_teams"].sort_values("sales_agent").to_dict("records"),
        "products": t["products"].sort_values("sales_price").to_dict("records"),
        "accounts": sorted(acc["account"].tolist()),
        "sectors": sorted(acc["sector"].dropna().unique().tolist()),
        "locations": sorted(acc["office_location"].dropna().unique().tolist()),
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _to_date(v) -> date | None:
    if v is None or (isinstance(v, str) and not v) or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def validate_opportunity(rec: dict, path: Path = STORE_PATH, today: date | None = None) -> list[str]:
    """Return a list of problems (empty list = valid)."""
    errors = []
    today = today or date.today()
    t = read_tables(path)
    stage = rec.get("deal_stage")
    engage, close = _to_date(rec.get("engage_date")), _to_date(rec.get("close_date"))
    value = rec.get("close_value")

    if rec.get("sales_agent") not in set(t["sales_teams"]["sales_agent"]):
        errors.append("Choose a sales agent from the sales team.")
    if rec.get("product") not in set(t["products"]["product"]):
        errors.append("Choose a product from the product catalogue.")
    acc = rec.get("account")
    if acc not in (None, "", NOT_ASSIGNED) and acc not in set(t["accounts"]["account"]):
        errors.append(f"Account '{acc}' does not exist. Add it first under New account.")
    if stage not in config.VALID_STAGES:
        errors.append(f"Stage must be one of {', '.join(config.VALID_STAGES)}.")
    if stage in ("Engaging", "Won", "Lost") and engage is None:
        errors.append("An engage date is required once a deal has reached Engaging.")
    if stage == "Prospecting" and engage is not None:
        errors.append("Prospecting deals have not been engaged yet, so leave the engage date empty.")
    if stage in config.CLOSED_STAGES:
        if close is None:
            errors.append("Closed deals (Won/Lost) need a close date.")
        if acc in (None, "", NOT_ASSIGNED):
            errors.append("Closed deals must be linked to an account.")
    if stage in config.OPEN_STAGES and (close is not None or value not in (None, "")):
        errors.append("Open deals cannot have a close date or close value.")
    if stage == "Won" and not (value is not None and float(value) > 0):
        errors.append("Won deals need a close value greater than 0.")
    if stage == "Lost" and value not in (None, "") and float(value) != 0:
        errors.append("Lost deals have a close value of 0.")
    if engage and close and engage > close:
        errors.append("The engage date cannot be after the close date.")
    for name, d in (("Engage date", engage), ("Close date", close)):
        if d and d > today:
            errors.append(f"{name} cannot be in the future.")
    return errors


def validate_account(rec: dict, path: Path = STORE_PATH) -> list[str]:
    errors = []
    t = read_tables(path)
    name = (rec.get("account") or "").strip()
    if not name:
        errors.append("Account name is required.")
    elif name.lower() in {a.lower() for a in t["accounts"]["account"]} or name == NOT_ASSIGNED:
        errors.append(f"An account named '{name}' already exists.")
    if not (rec.get("sector") or "").strip():
        errors.append("Sector is required.")
    year = rec.get("year_established")
    if year is not None and not (1800 <= int(year) <= date.today().year):
        errors.append("Year established looks implausible.")
    for f in ("revenue", "employees"):
        if rec.get(f) is not None and float(rec[f]) < 0:
            errors.append(f"{f.capitalize()} cannot be negative.")
    sub = rec.get("subsidiary_of")
    if sub and sub not in set(t["accounts"]["account"]):
        errors.append("Parent company must be an existing account.")
    return errors


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
def new_opportunity_id(path: Path = STORE_PATH) -> str:
    with closing(_connect(path)) as con:
        existing = {r[0] for r in con.execute("SELECT opportunity_id FROM opportunities")}
    alphabet = string.ascii_uppercase + string.digits
    while True:
        oid = "".join(random.choices(alphabet, k=8))
        if oid not in existing:
            return oid


def _clean_opp(rec: dict) -> dict:
    stage = rec["deal_stage"]
    acc = rec.get("account")
    value = rec.get("close_value")
    if stage == "Lost":
        value = 0.0
    engage, close = _to_date(rec.get("engage_date")), _to_date(rec.get("close_date"))
    return {
        "sales_agent": rec["sales_agent"], "product": rec["product"],
        "account": None if acc in (None, "", NOT_ASSIGNED) else acc,
        "deal_stage": stage,
        "engage_date": engage.isoformat() if engage else None,
        "close_date": close.isoformat() if close else None,
        "close_value": float(value) if (value not in (None, "") and stage in config.CLOSED_STAGES) else None,
    }


def add_opportunity(rec: dict, path: Path = STORE_PATH) -> str:
    errors = validate_opportunity(rec, path)
    if errors:
        raise ValidationError(errors)
    row = _clean_opp(rec)
    row["opportunity_id"] = new_opportunity_id(path)
    row["source"], row["created_at"] = "user", datetime.now().isoformat(timespec="seconds")
    with closing(_connect(path)) as con, con:
        con.execute(f"INSERT INTO opportunities ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                    list(row.values()))
        _bump(con)
    return row["opportunity_id"]


def update_opportunity(opportunity_id: str, changes: dict, path: Path = STORE_PATH) -> None:
    """Move a deal through the pipeline (e.g. Engaging -> Won). Validated as a whole record."""
    with closing(_connect(path)) as con:
        cur = pd.read_sql("SELECT * FROM opportunities WHERE opportunity_id = ?", con, params=[opportunity_id])
    if cur.empty:
        raise ValidationError([f"Opportunity {opportunity_id} not found."])
    rec = cur.iloc[0].to_dict()
    rec = {k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in rec.items()}
    rec.update(changes)
    errors = validate_opportunity(rec, path)
    if errors:
        raise ValidationError(errors)
    row = _clean_opp(rec)
    row["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with closing(_connect(path)) as con, con:
        con.execute(f"UPDATE opportunities SET {', '.join(f'{k} = ?' for k in row)} WHERE opportunity_id = ?",
                    [*row.values(), opportunity_id])
        _bump(con)


def add_account(rec: dict, path: Path = STORE_PATH) -> str:
    errors = validate_account(rec, path)
    if errors:
        raise ValidationError(errors)
    row = {k: rec.get(k) for k in ACCOUNT_COLUMNS if k not in ("source", "created_at")}
    row["account"] = row["account"].strip()
    row["sector"] = row["sector"].strip().lower()
    row["subsidiary_of"] = row["subsidiary_of"] or None
    row["source"], row["created_at"] = "user", datetime.now().isoformat(timespec="seconds")
    with closing(_connect(path)) as con, con:
        con.execute(f"INSERT INTO accounts ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                    list(row.values()))
        _bump(con)
    return row["account"]


def user_entries(path: Path = STORE_PATH) -> dict[str, pd.DataFrame]:
    with closing(_connect(path)) as con:
        return {
            "opportunities": pd.read_sql("SELECT * FROM opportunities WHERE source='user' OR updated_at IS NOT NULL "
                                         "ORDER BY COALESCE(updated_at, created_at) DESC", con),
            "accounts": pd.read_sql("SELECT * FROM accounts WHERE source='user' ORDER BY created_at DESC", con),
        }


def delete_user_opportunity(opportunity_id: str, path: Path = STORE_PATH) -> None:
    with closing(_connect(path)) as con, con:
        n = con.execute("DELETE FROM opportunities WHERE opportunity_id = ? AND source = 'user'",
                        [opportunity_id]).rowcount
        if not n:
            raise ValidationError(["Only entries created in this app can be deleted."])
        _bump(con)


def delete_user_account(account: str, path: Path = STORE_PATH) -> None:
    with closing(_connect(path)) as con, con:
        used = con.execute("SELECT COUNT(*) FROM opportunities WHERE account = ?", [account]).fetchone()[0]
        if used:
            raise ValidationError([f"'{account}' still has {used} opportunities. Delete those first."])
        n = con.execute("DELETE FROM accounts WHERE account = ? AND source = 'user'", [account]).rowcount
        if not n:
            raise ValidationError(["Only accounts created in this app can be deleted."])
        _bump(con)
