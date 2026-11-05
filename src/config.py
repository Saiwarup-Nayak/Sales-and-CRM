"""Central configuration: data sources, local paths and analysis constants."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
MODELS_DIR = PROJECT_ROOT / "models"
SQLITE_PATH = DATA_DIR / "crm.db"
MANIFEST_PATH = RAW_DIR / "manifest.json"

# ---------------------------------------------------------------------------
# Primary source: CRM Sales Opportunities (Maven Analytics, public domain)
# https://github.com/ZeinabBagherifard/CRM-Sales-Opportunities  (branch: master)
# ---------------------------------------------------------------------------
CRM_REPO = "https://github.com/ZeinabBagherifard/CRM-Sales-Opportunities"
CRM_RAW_BASE = "https://raw.githubusercontent.com/ZeinabBagherifard/CRM-Sales-Opportunities/master"
CRM_FILES = {
    "sales_pipeline": "sales_pipeline.csv",
    "accounts": "accounts.csv",
    "products": "products.csv",
    "sales_teams": "sales_teams.csv",
    "data_dictionary": "data_dictionary.csv",
}

# ---------------------------------------------------------------------------
# Secondary source: LeadForge synthetic lead-scoring bundle (MIT licence).
# Used ONLY for the separate lead-scoring module; it describes a different,
# simulated company and is never joined to the CRM opportunity data.
# https://github.com/leadforge-dev/leadforge-datasets  (branch: main)
# ---------------------------------------------------------------------------
LEADFORGE_REPO = "https://github.com/leadforge-dev/leadforge-datasets"
LEADFORGE_RAW_BASE = (
    "https://raw.githubusercontent.com/leadforge-dev/leadforge-datasets/main/releases/v0.1.0-alpha/intermediate"
)
LEADFORGE_FILES = {
    "lead_scoring": "lead_scoring.csv",
    "lead_feature_dictionary": "feature_dictionary.csv",
}

REQUEST_TIMEOUT_S = 30

# Expected schemas (used by validation checks)
REQUIRED_COLUMNS = {
    "sales_pipeline": [
        "opportunity_id", "sales_agent", "product", "account",
        "deal_stage", "engage_date", "close_date", "close_value",
    ],
    "accounts": [
        "account", "sector", "year_established", "revenue",
        "employees", "office_location", "subsidiary_of",
    ],
    "products": ["product", "series", "sales_price"],
    "sales_teams": ["sales_agent", "manager", "regional_office"],
}

VALID_STAGES = ["Prospecting", "Engaging", "Won", "Lost"]
OPEN_STAGES = ["Prospecting", "Engaging"]
CLOSED_STAGES = ["Won", "Lost"]

# Known inconsistencies between the source tables, verified during inspection.
PRODUCT_NAME_FIXES = {"GTXPro": "GTX Pro"}
SECTOR_NAME_FIXES = {"technolgy": "technology"}

RANDOM_STATE = 42
