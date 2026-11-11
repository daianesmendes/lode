"""Integration test against a real Postgres. Runs when TEST_DATABASE_URL is set (CI sets it)."""

import os

import psycopg
import pytest

from lode.etl.extract import extract
from lode.etl.load import load
from lode.sector import SOFTWARE
from tests.test_extract import month  # noqa: F401  (fixture)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


def test_load_replaces_previous_month(month):  # noqa: F811
    data = extract(month, SOFTWARE)
    with psycopg.connect(URL, autocommit=True) as conn:
        for _ in range(2):  # loading twice must not duplicate rows
            result = load(conn, data, "2026-10", {"7107": "SAO PAULO"}, {"6201501": "Software"})
        assert result == {
            "companies": 2,
            "establishments": 3,
            "establishments_without_company": 0,
        }
        counts = conn.execute(
            "select (select count(*) from company), (select count(*) from establishment), "
            "(select month from load_info)"
        ).fetchone()
        assert counts == (2, 3, "2026-10")
        mei = conn.execute("select is_mei, legal_name from company where cnpj_basico = '55555555'")
        assert mei.fetchone() == (True, "MARIA SOUZA")


def test_load_contracts_replaces_previous_period():
    from datetime import date

    from lode.etl.load import load_contracts
    from lode.etl.pncp import slim
    from tests.test_pncp import record

    contracts = [slim(record(1)), slim(record(2))]
    contracts[1]["signed_on"] = "not a date"  # malformed values become NULL
    with psycopg.connect(URL, autocommit=True) as conn:
        for _ in range(2):
            result = load_contracts(conn, contracts, date(2026, 10, 1), date(2026, 10, 31), 10)
        assert result == {"contracts_read": 10, "contracts_kept": 2}
        rows = conn.execute(
            "select cnpj_basico, signed_on, buyer_sphere from public_contract order by id"
        ).fetchall()
        assert rows == [("11111111", date(2026, 9, 30), "M"), ("11111111", None, "M")]
