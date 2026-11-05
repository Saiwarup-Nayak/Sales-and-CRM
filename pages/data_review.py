"""Data review page: the complete source dataset (as published on GitHub) and every preprocessing step.

This page always reflects the original GitHub data, not entries added in the CRM.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import config
from src import preprocessing_review as rv
from src.data_loader import DataLoadError, load_crm_raw, manifest
from src.opportunity_model import EXCLUDED_FEATURES, FEATURES, InsufficientDataError, train_and_evaluate
from src.preprocessing import DataValidationError, prepare

# Palette (validated reference palette, light mode)
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK2, MUTED, GRID, AXIS, SURFACE = "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE_RAMP = ["#f0efec", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]

st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1400px;}
  [data-testid="stMetric"] {background: #ffffff; border: 1px solid rgba(11,11,11,0.10);
                            border-radius: 10px; padding: 12px 16px;}
  [data-testid="stMetricLabel"] p {color: #52514e; font-size: 0.85rem;}
  .stTabs [data-baseweb="tab-list"] {gap: 4px; flex-wrap: wrap;}
  .stTabs [data-baseweb="tab"] {padding: 6px 14px;}
  .note {color: #52514e; font-size: 0.92rem;}
</style>""", unsafe_allow_html=True)


def style(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor=SURFACE,
                      paper_bgcolor=SURFACE, font=dict(family="system-ui, Segoe UI, sans-serif", color=INK2),
                      legend=dict(orientation="h", y=1.12, x=0), bargap=0.25, hoverlabel=dict(bgcolor="white"))
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)
    return fig


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Downloading dataset from GitHub and preprocessing...")
def load(refresh_token: int):
    raw, fetched = load_crm_raw(refresh=refresh_token > 0)
    prep = prepare(raw)
    return raw, [f.__dict__ for f in fetched], prep


@st.cache_resource(show_spinner="Training and evaluating conversion models...")
def train_model(refresh_token: int):
    return train_and_evaluate(load(refresh_token)[2].master)


def with_predictions(master: pd.DataFrame, result) -> pd.DataFrame:
    """Add win_probability / predicted_to_convert next to deal_stage (open deals only)."""
    out = master.copy()
    if result is None:
        return out
    prob = result.scored_open["win_probability"]
    out["win_probability"] = out.index.map(prob)
    out["predicted_to_convert"] = pd.Series(pd.NA, index=out.index, dtype=object)
    has = out["win_probability"].notna()
    out.loc[has, "predicted_to_convert"] = (out.loc[has, "win_probability"] >= result.threshold).map({True: "Yes", False: "No"})
    cols = list(out.columns)
    i = cols.index("deal_stage") + 1
    new = ["predicted_to_convert", "win_probability"]
    return out[[c for c in cols[:i] if c not in new] + new + [c for c in cols[i:] if c not in new]]


with st.sidebar:
    st.header("Data source")
    st.markdown(f"[CRM Sales Opportunities]({config.CRM_REPO})  \nMaven Analytics, public domain. "
                "Fictitious B2B hardware seller.")
    if st.button("🔄 Refresh data from GitHub", width="stretch"):
        st.session_state["refresh"] = st.session_state.get("refresh", 0) + 1
        st.cache_data.clear()

try:
    raw, fetched, prep = load(st.session_state.get("refresh", 0))
except (DataLoadError, DataValidationError) as exc:
    st.error(f"**Data could not be loaded.** {exc}")
    st.stop()

master = prep.master
raw_join = rv.raw_joined(raw)
try:
    model = train_model(st.session_state.get("refresh", 0))
    model_error = None
except InsufficientDataError as exc:
    model, model_error = None, str(exc)
master_pred = with_predictions(master, model)

with st.sidebar:
    for f in fetched:
        if f.get("warning"):
            st.warning(f["warning"])
    m = manifest()
    if m:
        last = max(v["downloaded_at_utc"] for v in m.values())
        st.caption(f"Downloaded: {last} UTC  \nCached in `data/raw/crm/`")
    st.caption(f"Data snapshot date: {prep.snapshot_date:%Y-%m-%d}")

# ---------------------------------------------------------------------------
# Header + summary
# ---------------------------------------------------------------------------
st.title("CRM Sales Opportunities: Data Review")
st.markdown('<p class="note">The full dataset as loaded from GitHub, followed by each preprocessing step: '
            "what changed, how many rows, and why. Every figure is computed from the loaded files.</p>",
            unsafe_allow_html=True)

log = rv.cleaning_log(raw, prep)
miss = rv.missing_report(raw_join, master)
raw_rows = len(raw["sales_pipeline"])
c = st.columns(6)
c[0].metric("Opportunities (raw)", f"{raw_rows:,}")
c[1].metric("Opportunities (clean)", f"{len(master):,}", f"{len(master) - raw_rows:+,} rows", delta_color="off")
c[2].metric("Source tables", f"{len(config.REQUIRED_COLUMNS)}", f"{sum(len(raw[t]) for t in config.REQUIRED_COLUMNS):,} rows", delta_color="off")
fixed = int(log.loc[log["technique"].str.contains("map|spelling|Title|strip"), "rows affected"].sum())
c[3].metric("Values corrected", f"{fixed:,}")
c[4].metric("Missing cells (joined raw)", f"{int(raw_join.isna().sum().sum()):,}")
n_warn = sum(ch.status != "pass" for ch in prep.checks)
c[5].metric("Integrity checks", f"{len(prep.checks)}", f"{n_warn} need attention", delta_color="off")

tabs = st.tabs(["1 · Complete dataset", "2 · Data cleaning", "3 · Missing values", "4 · Normalisation",
                "5 · Outliers", "6 · Encoding", "7 · Feature engineering", "8 · Final dataset",
                "9 · Conversion prediction"])

# ---------------------------------------------------------------------------
# 1. Complete dataset
# ---------------------------------------------------------------------------
with tabs[0]:
    st.subheader("Complete dataset as published")
    st.dataframe(rv.table_overview(raw), hide_index=True, width="stretch")
    choice = st.radio("Table", ["Joined (all tables, raw keys)", "sales_pipeline", "accounts", "products",
                                "sales_teams", "data_dictionary"], horizontal=True)
    df = raw_join if choice.startswith("Joined") else raw[choice]
    if choice.startswith("Joined"):
        unmatched = int(raw_join["series"].isna().sum())
        st.info(f"The raw tables joined on their original keys. {unmatched:,} pipeline rows have no product "
                "attributes because the pipeline says 'GTXPro' and products.csv says 'GTX Pro'. Tab 2 fixes this.")
    q = st.text_input("Search all columns", placeholder="e.g. Won, GTXPro, Acme ...", key="search_raw")
    view = df
    if q:
        view = df[df.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)]
    st.caption(f"Showing {len(view):,} of {len(df):,} rows × {df.shape[1]} columns")
    st.dataframe(view, width="stretch", height=460)
    st.download_button("Download as CSV", view.to_csv(index=False).encode(), f"{choice.split()[0].lower()}_raw.csv")

    with st.expander("Column profile"):
        prof = pd.DataFrame({"dtype": df.dtypes.astype(str), "non-null": df.notna().sum(),
                             "missing": df.isna().sum(), "unique": df.nunique(),
                             "sample": [str(df[c].dropna().iloc[0]) if df[c].notna().any() else "-" for c in df.columns]})
        st.dataframe(prof.rename_axis("column").reset_index(), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# 2. Cleaning
# ---------------------------------------------------------------------------
with tabs[1]:
    st.subheader("What was cleaned, and how much")
    st.dataframe(log, hide_index=True, width="stretch",
                 column_config={"rows affected": st.column_config.NumberColumn(format="%d"),
                                "why": st.column_config.TextColumn(width="large")})
    act = log[log["rows affected"] > 0].copy()
    act["label"] = act["step"] + " · " + act["column"]
    fig = go.Figure(go.Bar(x=act["rows affected"], y=act["label"], orientation="h", marker_color=BLUE,
                           text=act["rows affected"].map("{:,}".format), textposition="outside",
                           hovertemplate="%{y}<br>%{x:,} rows<extra></extra>"))
    fig.update_layout(title="Rows affected per cleaning rule (rules with zero hits omitted)")
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(style(fig, 60 + 34 * len(act)), width="stretch")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Before / after: product name standardisation**")
        bad = raw["sales_pipeline"][raw["sales_pipeline"]["product"].isin(config.PRODUCT_NAME_FIXES)]
        ex = bad[["opportunity_id", "product"]].head(5).rename(columns={"product": "product (raw)"})
        ex["product (clean)"] = ex["opportunity_id"].map(master.set_index("opportunity_id")["product"])
        ex["series (raw join)"] = ex["opportunity_id"].map(raw_join.set_index("opportunity_id")["series"])
        ex["series (clean join)"] = ex["opportunity_id"].map(master.set_index("opportunity_id")["series"])
        st.dataframe(ex, hide_index=True, width="stretch")
    with col2:
        st.markdown("**Before / after: sector typo**")
        sec = pd.DataFrame({"raw": raw["accounts"]["sector"].value_counts(),
                            "clean": prep.tables["accounts"]["sector"].value_counts()}).fillna(0).astype(int)
        st.dataframe(sec.rename_axis("sector").reset_index(), hide_index=True, width="stretch")

    st.markdown("**Data integrity checks**")
    chk = rv.integrity_checks(prep)
    chk["status"] = chk["status"].map({"pass": "✅ pass", "warn": "⚠️ warn", "fail": "❌ fail"})
    st.dataframe(chk, hide_index=True, width="stretch")
    st.markdown("**Data type conversions**")
    dt = rv.dtype_changes(raw_join, master)
    st.dataframe(dt[dt["changed"]].drop(columns="changed"), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# 3. Missing values
# ---------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Missing values: raw vs clean")
    has = miss[(miss["missing (raw)"] > 0) | (miss["missing (clean)"] > 0)]
    fig = go.Figure()
    fig.add_bar(name="Raw (joined on raw keys)", x=has["column"], y=has["% raw"], marker_color=BLUE,
                hovertemplate="%{x}<br>%{y:.1f}% missing (raw)<extra></extra>")
    fig.add_bar(name="After cleaning", x=has["column"], y=has["% clean"], marker_color=ORANGE,
                hovertemplate="%{x}<br>%{y:.1f}% missing (clean)<extra></extra>")
    fig.update_layout(title="Share of rows missing, by column", barmode="group", yaxis_ticksuffix="%")
    st.plotly_chart(style(fig), width="stretch")
    st.dataframe(miss, hide_index=True, width="stretch",
                 column_config={"% raw": st.column_config.NumberColumn(format="%.1f%%"),
                                "% clean": st.column_config.NumberColumn(format="%.1f%%")})

    st.markdown("**Missingness by deal stage.** The pattern is structural, not random: each gap follows "
                "from the deal's stage.")
    mbs = rv.missing_by_stage(raw)
    z = mbs[["account", "engage_date", "close_date", "close_value"]].values
    fig = go.Figure(go.Heatmap(z=z, x=["account", "engage_date", "close_date", "close_value"],
                               y=[f"{s} ({n:,})" for s, n in zip(mbs["deal_stage"], mbs["deals"])],
                               colorscale=[[i / (len(BLUE_RAMP) - 1), c] for i, c in enumerate(BLUE_RAMP)],
                               zmin=0, zmax=100, text=[[f"{v:.0f}%" for v in r] for r in z], texttemplate="%{text}",
                               hovertemplate="%{y} · %{x}: %{z:.1f}% missing<extra></extra>",
                               colorbar=dict(title="% missing", ticksuffix="%"), xgap=2, ygap=2))
    st.plotly_chart(style(fig, 300), width="stretch")
    st.markdown('<p class="note">Approach: structural gaps are <b>kept</b>, because they carry meaning (an open deal '
                "has no close date), and flag columns are added. Missing account attributes are imputed only inside "
                "the model pipeline (median / 'missing' category), never written into the reported data. "
                "No rows are dropped for being incomplete.</p>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 4. Normalisation
# ---------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Normalisation and scaling of numeric columns")
    st.markdown('<p class="note">Scaling puts numeric features on comparable ranges for distance- or '
                "gradient-based models (e.g. logistic regression). Reported dashboards keep original units. "
                "Text normalisation (case, spelling, whitespace) is covered in tab 2.</p>", unsafe_allow_html=True)
    a, b = st.columns(2)
    col = a.selectbox("Column", list(rv.NUMERIC_COLUMNS), format_func=lambda k: f"{k}: {rv.NUMERIC_COLUMNS[k]}")
    method = b.selectbox("Method", list(rv.SCALERS))
    st.code(rv.SCALERS[method], language=None)
    s = rv.numeric_source(master, col)
    if col == "close_value":
        st.caption("close_value uses won deals only: lost deals are 0 by definition and open deals have no value.")
    elif col in ("revenue", "employees", "year_established"):
        st.caption("Account attributes are scaled once per account (85 accounts), not once per deal.")
    elif col == "sales_price":
        st.caption("List price is scaled once per product (7 products).")
    after = rv.scale(s, method)
    h1, h2 = st.columns(2)
    for holder, data, name, color in [(h1, s, "Before (original units)", BLUE), (h2, after, f"After: {method}", ORANGE)]:
        fig = go.Figure(go.Histogram(x=data, nbinsx=40, marker_color=color, marker_line=dict(color=SURFACE, width=1),
                                     hovertemplate="%{x}<br>%{y} values<extra></extra>"))
        fig.update_layout(title=name, showlegend=False)
        holder.plotly_chart(style(fig, 300), width="stretch")
    st.markdown("**Summary statistics, before vs after**")
    st.dataframe(rv.describe_before_after(s, method).round(4), width="stretch")
    with st.expander("Compare all methods for this column"):
        allm = pd.DataFrame({m_: rv.scale(s, m_).describe()[["mean", "std", "min", "50%", "max"]] for m_ in rv.SCALERS}).T
        allm["skewness"] = [rv.scale(s, m_).skew() for m_ in rv.SCALERS]
        st.dataframe(allm.round(4), width="stretch")
        st.caption("Min-Max, Z-score, Robust and decimal scaling are linear, so the shape and skewness stay the same. "
                   "Only the log transform reduces right skew.")

# ---------------------------------------------------------------------------
# 5. Outliers
# ---------------------------------------------------------------------------
with tabs[4]:
    st.subheader("Outlier detection (IQR and z-score)")
    out = rv.outlier_report(master)
    st.dataframe(out, hide_index=True, width="stretch",
                 column_config={"IQR lower fence": st.column_config.NumberColumn(format="%.1f"),
                                "IQR upper fence": st.column_config.NumberColumn(format="%.1f")})
    col = st.selectbox("Inspect column", list(rv.NUMERIC_COLUMNS), key="out_col")
    s = rv.numeric_source(master, col)
    if col == "close_value":
        bx = master[master["is_won"]]
        fig = go.Figure(go.Box(x=bx["product"], y=bx["close_value"], marker_color=BLUE, boxpoints="outliers",
                               line=dict(width=1.5), hovertemplate="%{x}<br>$%{y:,.0f}<extra></extra>"))
        fig.update_layout(title="Won deal value by product: high values are consistent with each product's price")
    else:
        fig = go.Figure(go.Box(y=s, name=col, marker_color=BLUE, boxpoints="outliers", line=dict(width=1.5)))
        fig.update_layout(title=f"Distribution of {col}")
    st.plotly_chart(style(fig, 360), width="stretch")
    st.markdown('<p class="note">Decision: outliers are <b>flagged, not removed or capped</b>. Large won values belong to '
                "the expensive products (GTK 500, GTX Plus Pro), and large accounts are real companies. Removing them "
                "would understate revenue.</p>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 6. Encoding
# ---------------------------------------------------------------------------
with tabs[5]:
    st.subheader("Categorical encoding")
    st.dataframe(rv.encoding_summary(master), hide_index=True, width="stretch")
    ex = rv.encode_examples(master)
    cols = st.columns(2)
    for i, (name, d) in enumerate(ex.items()):
        with cols[i % 2]:
            st.markdown(f"**{name}**")
            st.dataframe(d, hide_index=True, width="stretch")
    st.markdown('<p class="note">One-hot encoding is used for nominal categories (no order). Label encoding is shown '
                "for reference only, because it implies an order that products do not have. deal_stage is the target, "
                "so it is never used as a model input.</p>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 7. Feature engineering
# ---------------------------------------------------------------------------
with tabs[6]:
    st.subheader("Derived features")
    st.dataframe(rv.engineered_features(master), hide_index=True, width="stretch")
    st.subheader("Binning (discretisation)")
    bins = rv.binning_examples(master)
    cols = st.columns(3)
    for holder, (name, d) in zip(cols, bins.items()):
        fig = go.Figure(go.Bar(x=d["band"].astype(str), y=d.iloc[:, 1], marker_color=BLUE,
                               text=d.iloc[:, 1], textposition="outside",
                               hovertemplate="%{x}: %{y:,}<extra></extra>"))
        fig.update_layout(title=dict(text=name, font=dict(size=13)), showlegend=False)
        holder.plotly_chart(style(fig, 300), width="stretch")
    st.subheader("Integration (joins)")
    st.markdown(f"""
- `sales_pipeline` ⟶ `products` on **product** (many-to-one)
- `sales_pipeline` ⟶ `sales_teams` on **sales_agent** (many-to-one)
- `sales_pipeline` ⟶ `accounts` on **account** (many-to-one; left join keeps deals with no account)
- Row count preserved: **{len(raw['sales_pipeline']):,} → {len(master):,}**. Every join is validated as many-to-one.
""")

# ---------------------------------------------------------------------------
# 8. Final dataset
# ---------------------------------------------------------------------------
with tabs[7]:
    st.subheader("Final preprocessed dataset")
    a, b, c3 = st.columns(3)
    a.metric("Rows", f"{len(master_pred):,}")
    b.metric("Columns", f"{master_pred.shape[1]}", f"+{master.shape[1] - raw_join.shape[1]} engineered, +2 predicted",
             delta_color="off")
    c3.metric("Stored in SQLite", config.SQLITE_PATH.name, "table: opportunities", delta_color="off")
    if model is not None:
        st.info("**predicted_to_convert** and **win_probability** are filled for the open deals (Prospecting / "
                "Engaging). Closed deals already have a known outcome in `outcome`. The model is no better than "
                "chance on this data. See tab 9 before relying on these columns.")
    q = st.text_input("Search all columns", key="search_clean")
    view = master_pred
    if q:
        view = master_pred[master_pred.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)]
    st.caption(f"Showing {len(view):,} of {len(master_pred):,} rows")
    st.dataframe(view, width="stretch", height=460,
                 column_config={"win_probability": st.column_config.ProgressColumn(
                                    "win_probability", format="%.2f", min_value=0.0, max_value=1.0),
                                "close_value": st.column_config.NumberColumn(format="$%.0f"),
                                "won_revenue": st.column_config.NumberColumn(format="$%.0f"),
                                "est_open_value": st.column_config.NumberColumn(format="$%.0f"),
                                "engage_date": st.column_config.DateColumn(),
                                "close_date": st.column_config.DateColumn()})
    st.download_button("Download cleaned dataset (CSV)", view.to_csv(index=False).encode(), "opportunities_clean.csv")

# ---------------------------------------------------------------------------
# 9. Conversion prediction
# ---------------------------------------------------------------------------
with tabs[8]:
    st.subheader("Will an open opportunity convert (be won)?")
    st.markdown('<p class="note">This dataset has no separate lead records. Every row is a sales '
                "<b>opportunity</b>, so \"convert\" here means an open opportunity (Prospecting / Engaging) "
                "ending as <b>Won</b>. The model learns from the 6,711 closed deals and predicts the 2,089 open ones.</p>",
                unsafe_allow_html=True)
    if model is None:
        st.error(f"The model could not be trained: {model_error}")
        st.stop()

    for w in model.warnings:
        st.warning(w, icon="⚠️")

    test = model.comparison[model.comparison["split"] == "test"].set_index("model")
    tm = model.test_metrics
    base_acc = test.loc["Prior baseline (Dummy)", "accuracy"] if "Prior baseline (Dummy)" in test.index else float("nan")
    k = st.columns(5)
    k[0].metric("Selected model", model.best_model, "chosen on validation ROC-AUC", delta_color="off")
    k[1].metric("Test ROC-AUC", f"{tm['roc_auc']:.3f}", f"95% CI {model.auc_ci[0]:.2f}–{model.auc_ci[1]:.2f}", delta_color="off")
    k[2].metric("Test accuracy", f"{tm['accuracy']:.1%}", f"always-'Won' baseline: {base_acc:.1%}", delta_color="off")
    k[3].metric("Decision threshold", f"{model.threshold:.3f}", "tuned for balanced accuracy", delta_color="off")
    sc = model.scored_open
    n_yes = int((sc["win_probability"] >= model.threshold).sum())
    k[4].metric("Open deals predicted 'Yes'", f"{n_yes:,} / {len(sc):,}")
    st.caption("ROC-AUC 0.5 = random ranking, 1.0 = perfect. A confidence interval that contains 0.5 means the model "
               "cannot tell future wins from losses any better than chance.")

    st.markdown("**Predictions for open opportunities**")
    f1, f2, f3 = st.columns([1, 1, 2])
    pick = f1.selectbox("Predicted to convert", ["All", "Yes", "No"])
    stage = f2.selectbox("Stage", ["All", "Prospecting", "Engaging"])
    q = f3.text_input("Search (rep, product, account...)", key="search_pred")
    tbl = sc.assign(predicted_to_convert=(sc["win_probability"] >= model.threshold).map({True: "Yes", False: "No"}))
    tbl = tbl[["opportunity_id", "deal_stage", "predicted_to_convert", "win_probability", "sales_agent", "product",
               "account", "sector", "est_open_value", "expected_value_est", "open_age_days", "account_info_missing"]]
    if pick != "All":
        tbl = tbl[tbl["predicted_to_convert"] == pick]
    if stage != "All":
        tbl = tbl[tbl["deal_stage"] == stage]
    if q:
        tbl = tbl[tbl.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)]
    st.caption(f"{len(tbl):,} open opportunities, sorted by win probability")
    st.dataframe(tbl, hide_index=True, width="stretch", height=380,
                 column_config={"win_probability": st.column_config.ProgressColumn(format="%.2f", min_value=0.0, max_value=1.0),
                                "est_open_value": st.column_config.NumberColumn("est. value (list price)", format="$%.0f"),
                                "expected_value_est": st.column_config.NumberColumn("prob × est. value", format="$%.0f"),
                                "open_age_days": st.column_config.NumberColumn("days since engaged", format="%d")})
    st.download_button("Download predictions (CSV)", tbl.to_csv(index=False).encode(), "open_opportunity_predictions.csv")

    st.markdown("**How the model was evaluated**")
    si = model.split_info
    st.markdown(f"Chronological split on close date. **Train** {si['train']['rows']:,} deals "
                f"({si['train']['from']} to {si['train']['to']}), **validation** {si['validation']['rows']:,} "
                f"({si['validation']['from']} to {si['validation']['to']}), used to pick the model and threshold, and "
                f"**test** {si['test']['rows']:,} ({si['test']['from']} to {si['test']['to']}), scored once.")
    show = test.reset_index()[["model", "roc_auc", "accuracy", "balanced_accuracy", "precision", "recall", "f1", "brier"]]
    st.dataframe(show.round(3), hide_index=True, width="stretch")

    g1, g2 = st.columns(2)
    cm = model.confusion
    labels = [["True negative", "False positive"], ["False negative", "True positive"]]
    fig = go.Figure(go.Heatmap(z=cm, x=["Predicted Lost", "Predicted Won"], y=["Actual Lost", "Actual Won"],
                               colorscale=[[i / (len(BLUE_RAMP) - 1), c] for i, c in enumerate(BLUE_RAMP)],
                               text=[[f"{labels[i][j]}<br>{cm[i][j]:,}" for j in range(2)] for i in range(2)],
                               texttemplate="%{text}", showscale=False, xgap=2, ygap=2,
                               hovertemplate="%{y} · %{x}: %{z:,}<extra></extra>"))
    fig.update_layout(title=f"Confusion matrix (test, {model.best_model})")
    fig.update_yaxes(autorange="reversed")
    g1.plotly_chart(style(fig, 340), width="stretch")

    cal = model.calibration
    fig = go.Figure()
    fig.add_scatter(x=[0.3, 0.9], y=[0.3, 0.9], mode="lines", name="Perfect calibration",
                    line=dict(color=AXIS, width=1.5), hoverinfo="skip")
    fig.add_scatter(x=cal["mean_predicted"], y=cal["observed_win_rate"], mode="lines+markers", name="Model",
                    line=dict(color=BLUE, width=2), marker=dict(size=9, line=dict(color=SURFACE, width=2)),
                    hovertemplate="predicted %{x:.2f}<br>observed %{y:.2f}<extra></extra>")
    fig.update_layout(title="Calibration (test): predicted vs observed win rate",
                      xaxis_title="Mean predicted probability", yaxis_title="Observed win rate")
    g2.plotly_chart(style(fig, 340), width="stretch")

    with st.expander("Features used and excluded (leakage control)"):
        st.markdown("**Used** (known while a deal is still open): " + ", ".join(f"`{f}`" for f in FEATURES))
        st.dataframe(pd.DataFrame(EXCLUDED_FEATURES.items(), columns=["excluded column", "reason"]),
                     hide_index=True, width="stretch")
        imp = model.importance
        st.markdown("**Permutation importance on test** (drop in ROC-AUC when a feature is shuffled):")
        st.dataframe(imp.round(4), hide_index=True, width="stretch")
