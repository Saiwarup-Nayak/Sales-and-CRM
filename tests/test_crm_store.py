"""Tests for the CRM store: seeding, validation rules, writes, deletes and the version counter."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src import crm_store
from src.crm_store import ValidationError


@pytest.fixture()
def store(tmp_path):
    tables = {
        "products": pd.DataFrame({"product": ["GTX Basic", "MG Special"], "series": ["GTX", "MG"],
                                  "sales_price": [550, 55]}),
        "sales_teams": pd.DataFrame({"sales_agent": ["Ann", "Bob"], "manager": ["Max", "Max"],
                                     "regional_office": ["East", "West"]}),
        "accounts": pd.DataFrame({"account": ["Acme"], "sector": ["retail"], "year_established": [1990],
                                  "revenue": [100.0], "employees": [200], "office_location": ["United States"],
                                  "subsidiary_of": [None]}),
        "sales_pipeline": pd.DataFrame({
            "opportunity_id": ["A1", "A2", "A3"], "sales_agent": ["Ann", "Bob", "Ann"],
            "product": ["GTX Basic", "MG Special", "GTX Basic"], "account": ["Acme", "Acme", None],
            "deal_stage": ["Won", "Lost", "Engaging"],
            "engage_date": pd.to_datetime(["2017-01-01", "2017-01-05", "2017-02-01"]),
            "close_date": pd.to_datetime(["2017-02-01", "2017-01-20", None]),
            "close_value": [560.0, 0.0, None]}),
    }
    path = tmp_path / "crm_app.db"
    crm_store.init_store(tables, path)
    return path


def base(**kw):
    rec = {"sales_agent": "Ann", "product": "GTX Basic", "account": "Acme", "deal_stage": "Engaging",
           "engage_date": date(2017, 3, 1), "close_date": None, "close_value": None}
    rec.update(kw)
    return rec


def test_seed_and_master(store):
    master, snapshot = crm_store.load_master(store)
    assert len(master) == 3
    assert master["won_revenue"].sum() == 560.0
    assert snapshot == pd.Timestamp("2017-02-01")
    assert crm_store.version(store) == 1


def test_add_open_opportunity_bumps_version(store):
    oid = crm_store.add_opportunity(base(), store)
    master, _ = crm_store.load_master(store)
    row = master[master["opportunity_id"] == oid].iloc[0]
    assert row["deal_stage"] == "Engaging" and row["source"] == "user" and pd.isna(row["close_value"])
    assert crm_store.version(store) == 2


@pytest.mark.parametrize("changes, message", [
    ({"sales_agent": "Nobody"}, "sales agent"),
    ({"product": "Unknown"}, "product"),
    ({"account": "Ghost Inc"}, "does not exist"),
    ({"engage_date": None}, "engage date is required"),
    ({"deal_stage": "Prospecting"}, "leave the engage date empty"),
    ({"deal_stage": "Won", "close_date": date(2017, 3, 5), "close_value": 0}, "greater than 0"),
    ({"deal_stage": "Won", "close_date": None, "close_value": 100}, "need a close date"),
    ({"deal_stage": "Won", "close_date": date(2017, 2, 1), "close_value": 100}, "cannot be after the close date"),
    ({"deal_stage": "Lost", "close_date": date(2017, 3, 5), "account": None}, "linked to an account"),
    ({"close_date": date(2017, 3, 5)}, "Open deals cannot have a close date"),
    ({"engage_date": date(2999, 1, 1)}, "future"),
])
def test_invalid_opportunities_rejected(store, changes, message):
    with pytest.raises(ValidationError) as exc:
        crm_store.add_opportunity(base(**changes), store)
    assert any(message.lower() in e.lower() for e in exc.value.errors)
    assert crm_store.version(store) == 1  # nothing written


def test_lost_deal_value_forced_to_zero(store):
    oid = crm_store.add_opportunity(base(deal_stage="Lost", close_date=date(2017, 3, 5)), store)
    master, _ = crm_store.load_master(store)
    assert master.loc[master["opportunity_id"] == oid, "close_value"].iloc[0] == 0


def test_update_moves_deal_to_won(store):
    with pytest.raises(ValidationError):  # A3 has no account -> cannot close
        crm_store.update_opportunity("A3", {"deal_stage": "Won", "close_date": date(2017, 3, 1),
                                            "close_value": 600}, store)
    crm_store.update_opportunity("A3", {"deal_stage": "Won", "close_date": date(2017, 3, 1),
                                        "close_value": 600, "account": "Acme"}, store)
    master, _ = crm_store.load_master(store)
    assert master["won_revenue"].sum() == 1160.0
    assert crm_store.user_entries(store)["opportunities"]["opportunity_id"].tolist() == ["A3"]


def test_accounts_validation_and_delete_rules(store):
    with pytest.raises(ValidationError):
        crm_store.add_account({"account": "acme", "sector": "retail"}, store)  # case-insensitive duplicate
    name = crm_store.add_account({"account": "Northwind", "sector": "Retail", "year_established": 2001,
                                  "revenue": 50.0, "employees": 120, "office_location": "Kenya",
                                  "subsidiary_of": None}, store)
    oid = crm_store.add_opportunity(base(account=name), store)
    with pytest.raises(ValidationError):  # still has a deal
        crm_store.delete_user_account(name, store)
    with pytest.raises(ValidationError):  # original data cannot be deleted
        crm_store.delete_user_opportunity("A1", store)
    crm_store.delete_user_opportunity(oid, store)
    crm_store.delete_user_account(name, store)
    assert len(crm_store.read_tables(store)["accounts"]) == 1


def test_reset_keeps_version_monotonic(store):
    crm_store.add_opportunity(base(), store)
    v = crm_store.version(store)
    tables = crm_store.read_tables(store)
    tables["accounts"] = tables["accounts"].drop(columns=["source", "created_at"])
    crm_store.init_store(tables, store)
    assert crm_store.version(store) == v + 1
