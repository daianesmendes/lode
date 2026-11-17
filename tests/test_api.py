"""The HTTP API against a real Postgres (TEST_DATABASE_URL)."""

import json
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from lode.api.app import create_app
from lode.etl.load import SCHEMA
from lode.model.score import MAIN_ESTABLISHMENT

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


def load_companies(conn):
    """Three scored companies. B's headquarters is in another state: its São Paulo branch, the
    only establishment we have, stands for it."""
    conn.execute("insert into municipality values ('7107', 'SAO PAULO'), ('6291', 'CAMPINAS')")
    for cnpj, name, size, email in [
        ("11111111", "ALFA SOFTWARE LTDA", "05", "contato@alfa.example"),
        ("22222222", "BETA SISTEMAS LTDA", "01", None),
        ("33333333", "GAMA DADOS LTDA", "01", "gama@example.com"),
    ]:
        conn.execute(
            "insert into company (cnpj_basico, legal_name, legal_nature, capital, size_code, "
            "is_simples, is_mei, partners, partners_person, partners_company, "
            "partners_foreign) values (%s, %s, '2062', 1000, %s, false, false, 1, 1, 0, 0)",
            (cnpj, name, size),
        )
        conn.execute(
            "insert into establishment (cnpj, cnpj_basico, is_headquarters, trade_name, "
            "opened_on, cnae_main, cnaes_secondary, uf, municipality_code, phone1, email) "
            "values (%s, %s, %s, %s, '2015-01-01', '6201501', '{}', 'SP', %s, '1199999999', %s)",
            (
                cnpj + "000100",
                cnpj,
                cnpj != "22222222",
                f"{name.split()[0]} TECH",
                "6291" if cnpj == "33333333" else "7107",
                email,
            ),
        )
    conn.execute(
        "insert into company_score (cnpj_basico, score, rank, reasons) values "
        "('11111111', 0.9, 1, '{\"capital\": 2.0}'), "
        "('33333333', 0.2, 2, '{\"capital\": 0.5}'), "
        "('22222222', 0.01, 3, '{\"capital\": -1.0}')"
    )
    conn.execute(MAIN_ESTABLISHMENT)  # as the score command does


def test_companies_come_by_rank_without_contact_data(db, client):
    load_companies(db)
    page = client.get("/companies").json()
    assert page["total"] == 3
    assert [c["cnpj_basico"] for c in page["items"]] == ["11111111", "33333333", "22222222"]
    first = page["items"][0]
    assert first["size"] == "other" and first["municipality"] == "SAO PAULO"
    assert first["trade_name"] == "ALFA TECH"
    assert not {"email", "phone1", "phone2"} & set(first)
    assert page["items"][2]["municipality"] == "SAO PAULO"  # branch stands for the company


def test_companies_filters(db, client):
    load_companies(db)

    def ids(**params):
        return [c["cnpj_basico"] for c in client.get("/companies", params=params).json()["items"]]

    assert ids(size="micro") == ["33333333", "22222222"]
    assert ids(municipality="6291") == ["33333333"]
    assert ids(min_score=0.5) == ["11111111"]
    assert ids(q="beta") == ["22222222"]
    assert ids(q="gama tech") == ["33333333"]  # trade name


def test_companies_pagination(db, client):
    load_companies(db)
    page = client.get("/companies", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 3 and [c["rank"] for c in page["items"]] == [2]
    past_the_end = client.get("/companies", params={"offset": 10}).json()
    assert past_the_end["total"] == 3 and past_the_end["items"] == []
    assert client.get("/companies", params={"limit": 101}).status_code == 422
