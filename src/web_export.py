"""Batch jobs that feed the React/Node web app.

Python stays the analytics engine; the Node API serves the results.

    python -m src.web_export all          # ensure store + review + predictions
    python -m src.web_export predictions  # retrain on the CRM store, write scores + model report
    python -m src.web_export review       # preprocessing review of the GitHub source data
    python -m src.web_export reset        # re-seed the CRM store from GitHub, then predictions

Outputs
-------
* ``predictions`` table in ``data/crm_app.db`` (opportunity_id, win_probability, scored_at)
* ``data/web/model.json``  - evaluation report for the opportunity win model
* ``data/web/review.json`` - preprocessing review (cleaning log, missing values, outliers...)
* ``data/web/raw_<table>.json`` / ``clean.json`` - full tables for the data browser
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from contextlib import closing
from datetime import datetime

import numpy as np
import pandas as pd

from src import config, crm_store
from src import preprocessing_review as rv
from src.opportunity_model import (EXCLUDED_FEATURES, FEATURES, InsufficientDataError, train_and_evaluate)

WEB_DIR = config.DATA_DIR / "web"


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def _clean(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if (math.isnan(v) or math.isinf(v)) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (pd.Timestamp, datetime)):
        return None if pd.isna(v) else v.strftime("%Y-%m-%d")
    if v is pd.NaT or v is pd.NA:
        return None
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [_clean(x) for x in v]
    if isinstance(v, pd.DataFrame):
        return records(v)
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [{str(k): _clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def _write(name: str, payload) -> None:
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    (WEB_DIR / name).write_text(json.dumps(_clean(payload), separators=(",", ":")), encoding="utf-8")


# ---------------------------------------------------------------------------
# Predictions + model report
# ---------------------------------------------------------------------------
def export_predictions() -> dict:
    master, _ = crm_store.load_master()
    now = datetime.now().isoformat(timespec="seconds")
    try:
        r = train_and_evaluate(master)
    except InsufficientDataError as exc:
        _write("model.json", {"available": False, "error": str(exc), "scored_at": now})
        return {"available": False}

    scores = r.scored_open[["opportunity_id", "win_probability"]].copy()
    scores["scored_at"] = now
    with closing(sqlite3.connect(crm_store.STORE_PATH)) as con, con:
        con.execute("DROP TABLE IF EXISTS predictions")
        con.execute("CREATE TABLE predictions (opportunity_id TEXT PRIMARY KEY, win_probability REAL, scored_at TEXT)")
        con.executemany("INSERT INTO predictions VALUES (?, ?, ?)", scores.itertuples(index=False, name=None))

    roc = {}
    for name, (fpr, tpr) in r.roc.items():  # downsample curves for the browser
        idx = np.unique(np.linspace(0, len(fpr) - 1, min(len(fpr), 60)).astype(int))
        roc[name] = [{"fpr": float(fpr[i]), "tpr": float(tpr[i])} for i in idx]
    report = {
        "available": True, "scored_at": now, "best_model": r.best_model, "threshold": r.threshold,
        "test_metrics": r.test_metrics, "auc_ci": list(r.auc_ci), "confusion": r.confusion.tolist(),
        "calibration": records(r.calibration), "roc": roc, "importance": records(r.importance),
        "comparison": records(r.comparison), "split_info": r.split_info, "warnings": r.warnings,
        "features": FEATURES, "excluded": [{"column": k, "reason": v} for k, v in EXCLUDED_FEATURES.items()],
        "n_scored": len(scores), "n_predicted_yes": int((scores["win_probability"] >= r.threshold).sum()),
    }
    _write("model.json", report)
    return {"available": True, "scored": len(scores), "auc": r.test_metrics["roc_auc"]}


# ---------------------------------------------------------------------------
# Preprocessing review (always from the original GitHub data)
# ---------------------------------------------------------------------------
def export_review() -> dict:
    from src.data_loader import load_crm_raw, manifest
    from src.preprocessing import prepare

    raw, _ = load_crm_raw()
    prep = prepare(raw)
    master = prep.master
    raw_join = rv.raw_joined(raw)

    numeric = {c: rv.numeric_source(master, c).round(4).tolist() for c in rv.NUMERIC_COLUMNS}
    won = master[master["is_won"]]
    box = {p: g["close_value"].tolist() for p, g in won.groupby("product")}
    review = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": config.CRM_REPO, "manifest": manifest(),
        "snapshot_date": prep.snapshot_date,
        "overview": records(rv.table_overview(raw)),
        "summary": {
            "raw_rows": len(raw["sales_pipeline"]), "clean_rows": len(master),
            "raw_columns": raw_join.shape[1], "clean_columns": master.shape[1],
            "missing_cells_raw": int(raw_join.isna().sum().sum()),
            "checks": len(prep.checks), "checks_attention": sum(c.status != "pass" for c in prep.checks),
        },
        "cleaning_log": records(rv.cleaning_log(raw, prep)),
        "integrity": records(rv.integrity_checks(prep)),
        "dtypes": records(rv.dtype_changes(raw_join, master)),
        "missing": records(rv.missing_report(raw_join, master)),
        "missing_by_stage": records(rv.missing_by_stage(raw)),
        "numeric_columns": rv.NUMERIC_COLUMNS, "numeric_values": numeric,
        "scalers": rv.SCALERS,
        "outliers": records(rv.outlier_report(master)),
        "won_value_by_product": box,
        "encoding": records(rv.encoding_summary(master)),
        "encoding_examples": {k: records(v) for k, v in rv.encode_examples(master).items()},
        "engineered": records(rv.engineered_features(master)),
        "binning": {k: records(v.astype({v.columns[0]: str})) for k, v in rv.binning_examples(master).items()},
        "sector_fix": records(pd.DataFrame({"raw": raw["accounts"]["sector"].value_counts(),
                                            "clean": prep.tables["accounts"]["sector"].value_counts()})
                              .fillna(0).astype(int).rename_axis("sector").reset_index()),
    }
    _write("review.json", review)
    for name in ["sales_pipeline", "accounts", "products", "sales_teams", "data_dictionary"]:
        _write(f"raw_{name}.json", {"columns": list(raw[name].columns), "rows": records(raw[name])})
    _write("raw_joined.json", {"columns": list(raw_join.columns), "rows": records(raw_join)})
    _write("clean.json", {"columns": list(master.columns), "rows": records(master)})
    return {"review": True, "rows": len(master)}


def main(argv: list[str]) -> int:
    job = argv[1] if len(argv) > 1 else "all"
    out = {}
    if job in ("all",):
        crm_store.ensure_store()
    if job == "reset":
        crm_store.seed_from_github(refresh=True)
    if job in ("all", "review"):
        out.update(export_review())
    if job in ("all", "predictions", "reset"):
        out.update(export_predictions())
    if job not in ("all", "review", "predictions", "reset"):
        print(json.dumps({"ok": False, "error": f"unknown job '{job}'"}))
        return 2
    print(json.dumps({"ok": True, "job": job, **_clean(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
