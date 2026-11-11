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
