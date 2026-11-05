# Pipeline CRM: Sales & CRM Intelligence System

A small CRM and analytics app built on the public **CRM Sales Opportunities** dataset
([ZeinabBagherifard/CRM-Sales-Opportunities](https://github.com/ZeinabBagherifard/CRM-Sales-Opportunities),
Maven Analytics, public domain, fictitious B2B hardware seller: 8,800 opportunities, 85 accounts, 7 products, 35 reps).

## Architecture

| Layer | Tech | Role |
|---|---|---|
| UI | React 18, Vite, React Router, React Query, Recharts, Framer Motion | Dashboard, pipeline board, CRUD, data review |
| API | Node 22.13+ / Express 5, built-in `node:sqlite` | Reads/writes `data/crm_app.db`, validates entries, computes dashboard aggregates |
| Analytics | Python (pandas, scikit-learn, statsmodels) | Downloads + cleans the GitHub data, trains the win model, builds the data review |

```
src/                 Python: data_loader, preprocessing, preprocessing_review, opportunity_model,
                     crm_store (SQLite store), web_export (batch jobs used by the API)
web/server/          Express API (src/routes.js, analytics.js, validation.js, jobs.js) + tests
web/client/          React app (src/pages/*, src/components/*)
app.py, pages/       Original Streamlit version (still works)
tests/               Python tests
data/                Generated: raw CSV cache, crm_app.db, web/*.json  (git-ignored)
```

The API runs the Python jobs (`python -m src.web_export ...`) itself: on first start it seeds the database;
after every write it re-scores open deals in the background; "Reset" re-downloads from GitHub.

## Run it

Prerequisites: Python 3.11+, Node 22.13+.

```bash
# 1. Python environment (once)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt      # macOS/Linux: .venv/bin/python -m pip ...

# 2. JS dependencies (once)
cd web
npm run setup

# 3. Build the UI and start the server -> http://localhost:4000
npm start
```

On first start the server downloads the dataset from GitHub and prepares the database (about 30 seconds).

Development with hot reload: `npm run dev:server` (port 4000) and `npm run dev:client` (http://localhost:5173, proxies `/api`).

Tests: `npm test` (API + validation, against a temporary copy of the DB) and `.venv\Scripts\python -m pytest tests`.

## Features

- **Dashboard**: 6 KPIs and 7 interactive charts, filtered by close date, office and product. Click through to the records.
- **Pipeline board**: drag an open deal to a later stage. A modal asks for the required details (close date, value, account).
- **Opportunities**: server-side search, filters, sorting and paging. Click a row to open a detail drawer and move the deal's stage. CSV export.
- **Accounts / Sales team**: card or table views, detail drawers with charts, and rep scorecards normalised for volume.
- **Add / my entries**: create deals and accounts, see and delete your own entries, reset to the GitHub data.
- **Ctrl+K command palette**: search deals, accounts and reps, or jump to a page.
- **Win prediction**: model comparison, ROC, calibration, confusion matrix and permutation importance.
- **Data review**: the raw dataset and every preprocessing step (cleaning log, missing values, live normalisation, outliers, encoding, features).

## Data rules enforced on every write

Prospecting has no dates or value. Engaging needs an engage date. Won/Lost need a close date and an account,
and Won needs a value above 0 (Lost is always 0). Dates must be in order and not in the future.
The same rules live in `web/server/src/validation.js` and `src/crm_store.py`.

## Important limitation: win prediction

The dataset has no lead or engagement history, so "convert" means an open **opportunity** ending as Won.
On a chronological test split every model, and the selected Decision Tree, scores **ROC-AUC ≈ 0.50
(95% CI 0.47–0.53)**, which is no better than chance. Accuracy (62%) is below the always-"Won" baseline (65%). The recorded
fields (rep, product, sector, company size) barely differ between won and lost deals. Probabilities are shown
for completeness and clearly labelled. Don't use them for decisions. A useful model would need engagement data
(calls, emails, meetings, stage history).

Other notes: open-deal value is estimated at list price (won deals close at a median 1.0× list price), and the
stage funnel is a snapshot of current stages, not stage-to-stage conversion (there is no stage history).
