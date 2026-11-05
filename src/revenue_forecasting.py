"""Monthly forecast of *recognised* (won) revenue.

The series is won revenue aggregated by close month. Only simple models are
appropriate for a short series: naive and historical-mean baselines, a linear
trend (OLS) and simple exponential smoothing. Models are compared on a
chronological holdout (the last ``HOLDOUT`` months) using MAE / RMSE / MAPE,
then the best is refit on all months to forecast ahead with 95% prediction
intervals.

Guardrails: no forecast is produced with fewer than ``MIN_MONTHS`` complete
months, and the horizon is capped (seasonality cannot be estimated with < 24
months). This is separate from the expected value of open opportunities,
which has no close dates and therefore cannot be placed on a monthly timeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.holtwinters import SimpleExpSmoothing

MIN_MONTHS = 9
HOLDOUT = 3
Z95 = 1.96


@dataclass
class ForecastResult:
    sufficient: bool
    message: str
    history: pd.DataFrame
    holdout: pd.DataFrame = field(default_factory=pd.DataFrame)
    metrics: pd.DataFrame = field(default_factory=pd.DataFrame)
    best_model: str | None = None
    forecast: pd.DataFrame = field(default_factory=pd.DataFrame)
    horizon: int = 0
    notes: list[str] = field(default_factory=list)


def monthly_revenue(master: pd.DataFrame) -> tuple[pd.Series, list[str]]:
    """Won revenue per close month, gap-filled, with incomplete edge months dropped."""
    notes = []
    won = master[master["is_won"] & master["close_date"].notna()]
    if won.empty:
        return pd.Series(dtype=float), ["No won deals in selection."]
    s = won.groupby(won["close_date"].dt.to_period("M"))["won_revenue"].sum()
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"), fill_value=0.0)
    last_day = master["close_date"].max()
    if last_day < (last_day.to_period("M").to_timestamp(how="end") - pd.Timedelta(days=3)).normalize():
        notes.append(f"Dropped {s.index[-1]} as an incomplete month (data ends {last_day:%Y-%m-%d}).")
        s = s.iloc[:-1]
    first_day = master["close_date"].min()
    if first_day.day > 4:
        notes.append(f"Dropped {s.index[0]} as an incomplete month (data starts {first_day:%Y-%m-%d}).")
        s = s.iloc[1:]
    s.index = s.index.to_timestamp()
    return s.astype(float), notes


# --- model functions: (train series, horizon) -> (point forecast array, std-error array) -------------
def _naive(y: pd.Series, h: int):
    sigma = np.std(np.diff(y.values), ddof=1) if len(y) > 2 else np.nan
    return np.repeat(y.iloc[-1], h), sigma * np.sqrt(np.arange(1, h + 1))


def _mean(y: pd.Series, h: int):
    sigma = y.std(ddof=1)
    return np.repeat(y.mean(), h), np.repeat(sigma * np.sqrt(1 + 1 / len(y)), h)


def _linear_trend(y: pd.Series, h: int):
    t = np.arange(len(y))
    fit = sm.OLS(y.values, sm.add_constant(t)).fit()
    tf = sm.add_constant(np.arange(len(y), len(y) + h), has_constant="add")
    pred = fit.get_prediction(tf).summary_frame(alpha=0.05)
    se = (pred["obs_ci_upper"] - pred["mean"]).values / Z95
    return pred["mean"].values, se


def _ses(y: pd.Series, h: int):
    fit = SimpleExpSmoothing(y.values, initialization_method="estimated").fit()
    alpha = fit.params["smoothing_level"]
    sigma = np.std(y.values - fit.fittedvalues, ddof=1)
    se = sigma * np.sqrt(1 + (np.arange(1, h + 1) - 1) * alpha**2)
    return fit.forecast(h), se


MODELS = {
    "Naive (last month)": _naive,
    "Historical mean": _mean,
    "Linear trend (OLS)": _linear_trend,
    "Simple exponential smoothing": _ses,
}
BASELINES = {"Naive (last month)", "Historical mean"}


def _errors(actual: np.ndarray, pred: np.ndarray) -> dict:
    e = actual - pred
    with np.errstate(divide="ignore", invalid="ignore"):
        mape = np.nanmean(np.abs(e) / np.where(actual == 0, np.nan, np.abs(actual))) * 100
    return {"MAE": float(np.mean(np.abs(e))), "RMSE": float(np.sqrt(np.mean(e**2))), "MAPE_%": float(mape)}


def forecast_revenue(master: pd.DataFrame, horizon: int = 3) -> ForecastResult:
    y, notes = monthly_revenue(master)
    history = y.rename("won_revenue").rename_axis("month").reset_index()
    n = len(y)
    if n < MIN_MONTHS:
        return ForecastResult(False, f"Only {n} complete months of won revenue are available; at least "
                                     f"{MIN_MONTHS} are needed for a holdout-validated forecast. Showing the "
                                     "historical trend only.", history, notes=notes)
    max_h = 3 if n < 24 else 6
    if horizon > max_h:
        notes.append(f"Horizon capped at {max_h} months because only {n} months of history exist.")
    h = min(horizon, max_h)
    notes.append("Seasonality is not modelled: it needs at least 24 months of history.")

    train, test = y.iloc[:-HOLDOUT], y.iloc[-HOLDOUT:]
    hold_rows, metric_rows = [], []
    for name, fn in MODELS.items():
        try:
            pred, _ = fn(train, HOLDOUT)
        except Exception as exc:
            notes.append(f"{name} failed on holdout: {exc}")
            continue
        metric_rows.append({"model": name, "baseline": name in BASELINES, **_errors(test.values, np.asarray(pred))})
        hold_rows += [{"month": m, "model": name, "forecast": float(p), "actual": float(a)}
                      for m, p, a in zip(test.index, pred, test.values)]
    metrics = pd.DataFrame(metric_rows).sort_values("MAE").reset_index(drop=True)
    best = metrics.iloc[0]["model"]
    best_baseline_mae = metrics.loc[metrics["baseline"], "MAE"].min()
    if best in BASELINES:
        notes.append(f"No model beat the simple baselines on the holdout; '{best}' is used.")
    else:
        gain = (1 - metrics.iloc[0]["MAE"] / best_baseline_mae) * 100
        notes.append(f"'{best}' reduced holdout MAE by {gain:.0f}% versus the best baseline.")

    pred, se = MODELS[best](y, h)
    months = pd.date_range(y.index[-1] + pd.offsets.MonthBegin(1), periods=h, freq="MS")
    fc = pd.DataFrame({"month": months, "forecast": np.maximum(pred, 0),
                       "lower_95": np.maximum(pred - Z95 * se, 0), "upper_95": pred + Z95 * se})
    msg = (f"{best} forecast for the next {h} months, validated on a {HOLDOUT}-month holdout "
           f"({n} months of history).")
    return ForecastResult(True, msg, history, pd.DataFrame(hold_rows), metrics, best, fc, h, notes)
