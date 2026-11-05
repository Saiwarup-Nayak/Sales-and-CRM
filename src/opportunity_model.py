"""Opportunity win prediction (opportunity-level, NOT lead scoring).

Target: ``is_won`` for opportunities whose final outcome is known (Won/Lost).
Open opportunities (Prospecting/Engaging) are excluded from training and scored
afterwards.

Leakage controls
----------------
* Excluded: ``opportunity_id`` and ``account`` (identifiers), ``deal_stage``
  (is the label), ``close_date``, ``close_value`` and everything derived from
  them (revenue, sales cycle, close month) - all only known after the outcome.
* ``engage_date`` features are excluded: Prospecting deals do not have one, and
  with a chronological split they would encode the period rather than the deal.
* Features used are attributes known when a deal is in the pipeline: rep,
  manager, office, product, list price, and account firmographics.

Validation design
-----------------
Chronological split on ``close_date``: oldest 60% train, next 20% validation
(model + threshold selection), newest 20% test (reported once). The selected
model is then refit on all closed deals to score open ones.

Class imbalance
---------------
The imbalance is mild (~63% won). Models are trained unweighted so predicted
probabilities stay calibrated; the decision threshold is tuned on the
validation split to maximise balanced accuracy, and balanced accuracy / PR-AUC
are reported alongside accuracy.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score, brier_score_loss,
                             confusion_matrix, f1_score, log_loss, precision_score, recall_score, roc_auc_score,
                             roc_curve)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from src import config

CATEGORICAL_FEATURES = ["sales_agent", "manager", "regional_office", "product", "series",
                        "sector", "office_location", "is_subsidiary"]
NUMERIC_FEATURES = ["sales_price", "year_established", "revenue", "employees"]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
EXCLUDED_FEATURES = {
    "opportunity_id": "identifier",
    "account": "identifier (account attributes are used instead)",
    "deal_stage": "is the target",
    "close_date": "only known after the outcome",
    "close_value / won_revenue": "only known after the outcome (0 for every lost deal)",
    "sales_cycle_days": "needs close_date - leaks the outcome",
    "engage_date": "missing for Prospecting deals; encodes time period under a chronological split",
}
MIN_TRAIN_ROWS = 200
MIN_CLASS_COUNT = 20


class InsufficientDataError(ValueError):
    pass


@dataclass
class OpportunityModelResult:
    comparison: pd.DataFrame
    best_model: str
    threshold: float
    test_metrics: dict
    confusion: np.ndarray
    calibration: pd.DataFrame
    roc: dict
    importance: pd.DataFrame
    scored_open: pd.DataFrame
    split_info: dict
    auc_ci: tuple[float, float]
    final_pipeline: Pipeline
    warnings: list[str] = field(default_factory=list)


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    for c in CATEGORICAL_FEATURES:
        if c == "is_subsidiary":
            known = df["account_known"] if "account_known" in df else pd.Series(True, index=df.index)
            sub = pd.Series(np.where(df["subsidiary_of"].notna(), "yes", "no"), index=df.index, dtype=object)
            X[c] = sub.where(known, np.nan)
        else:
            X[c] = df[c]
    for c in NUMERIC_FEATURES:
        X[c] = pd.to_numeric(df[c], errors="coerce")
    # Unknown accounts: treat account attributes as missing (imputed), not as a category seen in training.
    if "account_known" in df:
        X.loc[~df["account_known"], ["sector", "office_location"]] = np.nan
    X[CATEGORICAL_FEATURES] = X[CATEGORICAL_FEATURES].astype(object)
    return X


def _preprocessor(scale: bool) -> ColumnTransformer:
    num_steps = [("impute", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("scale", StandardScaler()))
    cat = Pipeline([("impute", SimpleImputer(strategy="constant", fill_value="__missing__")),
                    ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse_output=False))])
    return ColumnTransformer([("num", Pipeline(num_steps), NUMERIC_FEATURES),
                              ("cat", cat, CATEGORICAL_FEATURES)])


def candidate_models() -> dict[str, Pipeline]:
    rs = config.RANDOM_STATE
    return {
        "Prior baseline (Dummy)": Pipeline([("prep", _preprocessor(False)),
                                            ("clf", DummyClassifier(strategy="prior"))]),
        "Logistic Regression": Pipeline([("prep", _preprocessor(True)),
                                         ("clf", LogisticRegression(C=0.5, max_iter=2000))]),
        "Decision Tree": Pipeline([("prep", _preprocessor(False)),
                                   ("clf", DecisionTreeClassifier(max_depth=5, min_samples_leaf=50,
                                                                  random_state=rs))]),
        "Random Forest": Pipeline([("prep", _preprocessor(False)),
                                   ("clf", RandomForestClassifier(n_estimators=300, min_samples_leaf=20,
                                                                  max_features="sqrt", n_jobs=-1,
                                                                  random_state=rs))]),
        "Gradient Boosting": Pipeline([("prep", _preprocessor(False)),
                                       ("clf", HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05,
                                                                              max_iter=200, random_state=rs))]),
    }


def chronological_split(closed: pd.DataFrame, train_frac=0.6, valid_frac=0.2):
    closed = closed.sort_values(["close_date", "opportunity_id"])
    n = len(closed)
    i1, i2 = int(n * train_frac), int(n * (train_frac + valid_frac))
    return closed.iloc[:i1], closed.iloc[i1:i2], closed.iloc[i2:]


def classification_metrics(y, proba, threshold: float) -> dict:
    pred = (proba >= threshold).astype(int)
    two_classes = len(np.unique(y)) == 2
    return {
        "accuracy": accuracy_score(y, pred),
        "balanced_accuracy": balanced_accuracy_score(y, pred),
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
        "roc_auc": roc_auc_score(y, proba) if two_classes else np.nan,
        "pr_auc": average_precision_score(y, proba) if two_classes else np.nan,
        "brier": brier_score_loss(y, proba),
        "log_loss": log_loss(y, np.clip(proba, 1e-6, 1 - 1e-6), labels=[0, 1]),
    }


def tune_threshold(y, proba) -> float:
    """Threshold that maximises balanced accuracy on the given (validation) data."""
    grid = np.unique(np.quantile(proba, np.linspace(0.02, 0.98, 97)))
    if len(grid) == 0:
        return 0.5
    scores = [balanced_accuracy_score(y, (proba >= t).astype(int)) for t in grid]
    return float(grid[int(np.argmax(scores))])


def bootstrap_auc_ci(y, proba, n_boot: int = 500, seed: int = config.RANDOM_STATE) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    y, proba = np.asarray(y), np.asarray(proba)
    aucs = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if len(np.unique(y[idx])) == 2:
            aucs.append(roc_auc_score(y[idx], proba[idx]))
    return (float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))) if aucs else (np.nan, np.nan)


def train_and_evaluate(master: pd.DataFrame) -> OpportunityModelResult:
    closed = master[master["is_closed"]].copy()
    warnings: list[str] = []
    if len(closed) < MIN_TRAIN_ROWS:
        raise InsufficientDataError(f"Only {len(closed)} closed opportunities; need at least {MIN_TRAIN_ROWS}.")
    counts = closed["is_won"].value_counts()
    if len(counts) < 2 or counts.min() < MIN_CLASS_COUNT:
        raise InsufficientDataError(f"Both outcomes need >= {MIN_CLASS_COUNT} examples; got {counts.to_dict()}.")

    train, valid, test = chronological_split(closed)
    for name, part in [("validation", valid), ("test", test)]:
        if part["is_won"].nunique() < 2:
            raise InsufficientDataError(f"The {name} split contains a single class; cannot evaluate.")
    Xtr, ytr = build_feature_frame(train), train["is_won"].astype(int).values
    Xva, yva = build_feature_frame(valid), valid["is_won"].astype(int).values
    Xte, yte = build_feature_frame(test), test["is_won"].astype(int).values

    rows, fitted = [], {}
    for name, pipe in candidate_models().items():
        try:
            pipe.fit(Xtr, ytr)
        except Exception as exc:  # keep going if one model fails
            warnings.append(f"{name} failed to train: {exc}")
            continue
        p_va = pipe.predict_proba(Xva)[:, 1]
        thr = 0.5 if name.startswith("Prior") else tune_threshold(yva, p_va)
        fitted[name] = (pipe, thr)
        rows.append({"model": name, "split": "validation", "threshold": thr,
                     **classification_metrics(yva, p_va, thr)})
    candidates = [r for r in rows if not r["model"].startswith("Prior")]
    if not candidates:
        raise InsufficientDataError("Every candidate model failed to train.")
    best = max(candidates, key=lambda r: r["roc_auc"])
    best_name, threshold = best["model"], best["threshold"]

    # Report every model on the untouched test split (refit on train+valid), threshold fixed from validation.
    trva = pd.concat([train, valid])
    Xtrva, ytrva = build_feature_frame(trva), trva["is_won"].astype(int).values
    test_probas = {}
    for name, (_, thr) in fitted.items():
        pipe = candidate_models()[name].fit(Xtrva, ytrva)
        p_te = pipe.predict_proba(Xte)[:, 1]
        test_probas[name] = (pipe, p_te)
        rows.append({"model": name, "split": "test", "threshold": thr, **classification_metrics(yte, p_te, thr)})
    comparison = pd.DataFrame(rows)

    best_pipe, p_best = test_probas[best_name]
    test_metrics = classification_metrics(yte, p_best, threshold)
    cm = confusion_matrix(yte, (p_best >= threshold).astype(int), labels=[0, 1])
    frac_pos, mean_pred = calibration_curve(yte, p_best, n_bins=8, strategy="quantile")
    calib = pd.DataFrame({"mean_predicted": mean_pred, "observed_win_rate": frac_pos})
    roc = {}
    for name, (_, p) in test_probas.items():
        fpr, tpr, _ = roc_curve(yte, p)
        roc[name] = (fpr, tpr)
    auc_ci = bootstrap_auc_ci(yte, p_best)

    imp = permutation_importance(best_pipe, Xte, yte, scoring="roc_auc", n_repeats=10,
                                 random_state=config.RANDOM_STATE, n_jobs=1)
    importance = (pd.DataFrame({"feature": FEATURES, "auc_drop_mean": imp.importances_mean,
                                "auc_drop_std": imp.importances_std})
                  .sort_values("auc_drop_mean", ascending=False).reset_index(drop=True))

    if test_metrics["roc_auc"] < 0.6:
        warnings.append(
            f"Weak discrimination: test ROC-AUC = {test_metrics['roc_auc']:.3f} "
            f"(95% CI {auc_ci[0]:.3f}-{auc_ci[1]:.3f}). The recorded fields carry little signal about "
            "outcomes; treat probabilities as close to the base rate and do not use them for hard decisions.")

    # Final model on all closed deals -> score open opportunities.
    final = candidate_models()[best_name].fit(build_feature_frame(closed), closed["is_won"].astype(int).values)
    open_ = master[master["is_open"]].copy()
    if len(open_):
        open_["win_probability"] = final.predict_proba(build_feature_frame(open_))[:, 1]
        open_["expected_value_est"] = open_["win_probability"] * open_["est_open_value"]
        open_["account_info_missing"] = ~open_["account_known"]
        n_missing = int(open_["account_info_missing"].sum())
        if n_missing:
            warnings.append(f"{n_missing:,} of {len(open_):,} open opportunities have no account recorded; "
                            "their scores rely on rep and product only (account attributes imputed).")
    scored = open_.sort_values("win_probability", ascending=False) if len(open_) else open_

    split_info = {
        part: {"rows": len(d), "win_rate": float(d["is_won"].mean()),
               "from": f"{d['close_date'].min():%Y-%m-%d}", "to": f"{d['close_date'].max():%Y-%m-%d}"}
        for part, d in [("train", train), ("validation", valid), ("test", test)]
    }
    return OpportunityModelResult(comparison, best_name, threshold, test_metrics, cm, calib, roc, importance,
                                  scored, split_info, auc_ci, final, warnings)


def save_artifacts(result: OpportunityModelResult) -> None:
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(result.final_pipeline, config.MODELS_DIR / "opportunity_model.joblib")
    payload = {
        "best_model": result.best_model,
        "threshold": result.threshold,
        "test_metrics": result.test_metrics,
        "test_roc_auc_95ci": result.auc_ci,
        "confusion_matrix_[[tn,fp],[fn,tp]]": result.confusion.tolist(),
        "split_info": result.split_info,
        "features": FEATURES,
        "excluded_features": EXCLUDED_FEATURES,
        "warnings": result.warnings,
        "comparison": result.comparison.to_dict(orient="records"),
    }
    (config.MODELS_DIR / "opportunity_model_metrics.json").write_text(json.dumps(payload, indent=2, default=float))
