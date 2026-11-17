"""The HTTP API against a real Postgres (TEST_DATABASE_URL)."""

import json
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from lode.api.app import create_app
from lode.etl.load import SCHEMA

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

METRICS = {
    "chosen": "logistic",
    "holdout": {
        "logistic": {
            "base_rate": 0.009,
            "pr_auc": 0.176,
            "roc_auc": 0.91,
            "precision_at_100": 0.28,
            "lift_at_10pct": 7.8,
        }
    },
    "holdout_pr_auc_interval": {"logistic": [0.135, 0.233]},
}


@pytest.fixture
def db():
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text())
        conn.execute(
            "truncate company_score, score_info, public_contract, pncp_info, establishment, "
            "company, municipality, load_info"
        )
        yield conn


@pytest.fixture
def client():
    with TestClient(create_app(URL)) as client:
        yield client


def load_meta(conn):
    conn.execute(
        "insert into load_info (month, companies, establishments, rows_read) "
        "values ('2026-10', 3, 3, '{}')"
    )
    conn.execute(
        "insert into pncp_info (period_start, period_end, contracts_read, contracts_kept) "
        "values ('2025-11-01', '2026-10-31', 100, 10)"
    )
    conn.execute(
        "insert into score_info (cutoff, model_version, model, companies, metrics) "
        "values ('2026-11-01', 'abc123', 'LogisticRegression', 3, %s)",
        (json.dumps(METRICS),),
    )


def test_health(db, client):
    assert client.get("/health").json() == {"status": "ok"}


def test_meta_before_scoring_says_so(db, client):
    response = client.get("/meta")
    assert response.status_code == 503


def test_meta_tells_where_the_data_comes_from_and_how_good_the_model_is(db, client):
    load_meta(db)
    meta = client.get("/meta").json()
    assert meta["receita_month"] == "2026-10"
    assert (meta["contracts_from"], meta["contracts_to"]) == ("2025-11-01", "2026-10-31")
    assert meta["score_cutoff"] == "2026-11-01" and meta["companies"] == 3
    assert meta["model_version"] == "abc123"
    assert meta["holdout"] == {
        "pr_auc": 0.176,
        "pr_auc_interval": [0.135, 0.233],
        "precision_at_100": 0.28,
        "lift_at_10pct": 7.8,
        "base_rate": 0.009,
    }


def test_docs_are_published(db, client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/meta"} <= set(paths)
