"""The cutoff rules of the feature table, against a real Postgres (TEST_DATABASE_URL)."""

import os
from datetime import date

import psycopg
import pytest

from lode.etl.load import SCHEMA
from lode.model.features import build

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

CUTOFF = date(2025, 11, 1)
END = date(2026, 11, 1)


def company(cnpj_basico, simples_since=None, first_partner_since=date(2015, 1, 1)):
    return (
        cnpj_basico,
        f"COMPANY {cnpj_basico}",
        "2062",
        10000,
        "01",
        simples_since is not None,
        simples_since,
        False,
        None,
        2,
        2,
        0,
        0,
        4,
        6,
        first_partner_since,
    )


def establishment(cnpj_basico, branch, opened_on, hq=True, city="7107"):
    cnpj = f"{cnpj_basico}{branch:04d}00"
    return (cnpj, cnpj_basico, hq, opened_on, "6201501", ["6202300"], "SP", city)


@pytest.fixture
def conn():
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text())
        conn.execute("truncate public_contract, pncp_info, establishment, company")
        conn.execute(
            "insert into pncp_info (period_start, period_end, contracts_read, contracts_kept) "
            "values ('2025-11-01', '2026-10-31', 0, 0)"
        )
        yield conn


def insert(conn, companies, establishments, contracts=()):
    with conn.cursor() as cur:
        cur.executemany(
            "insert into company values "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            companies,
        )
        cur.executemany(
            "insert into establishment (cnpj, cnpj_basico, is_headquarters, opened_on, "
            "cnae_main, cnaes_secondary, uf, municipality_code) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s)",
            establishments,
        )
        cur.executemany(
            "insert into public_contract (id, cnpj, cnpj_basico, published_at) "
            "values (%s, %s, %s, %s)",
            contracts,
        )


def by_id(rows):
    return {row["cnpj_basico"]: row for row in rows}


def test_company_opened_after_cutoff_is_left_out(conn):
    insert(
        conn,
        [company("11111111"), company("22222222")],
        [
            establishment("11111111", 1, date(2020, 1, 1)),
            establishment("22222222", 1, date(2026, 3, 1)),
        ],
    )
    assert list(by_id(build(conn, CUTOFF, END))) == ["11111111"]


def test_branch_opened_after_cutoff_is_not_counted(conn):
    insert(
        conn,
        [company("11111111")],
        [
            establishment("11111111", 1, date(2015, 11, 1)),
            establishment("11111111", 2, date(2026, 1, 10), hq=False, city="6291"),
        ],
    )
    row = build(conn, CUTOFF, END)[0]
    assert row["establishments"] == 1
    assert row["hq_in_capital"] is True
    assert round(row["age_years"]) == 10


def test_simples_and_partners_are_rebuilt_for_the_cutoff(conn):
    insert(
        conn,
        [
            company("11111111", simples_since=date(2018, 1, 1)),
            company(
                "22222222", simples_since=date(2026, 1, 1), first_partner_since=date(2026, 2, 1)
            ),
        ],
        [
            establishment("11111111", 1, date(2017, 5, 1)),
            establishment("22222222", 1, date(2017, 5, 1)),
        ],
    )
    rows = by_id(build(conn, CUTOFF, END))
    assert (rows["11111111"]["simples"], rows["11111111"]["partners_changed"]) == (True, False)
    assert (rows["22222222"]["simples"], rows["22222222"]["partners_changed"]) == (False, True)


def test_label_uses_only_contracts_inside_the_window(conn):
    insert(
        conn,
        [company("11111111"), company("22222222"), company("33333333")],
        [establishment(c, 1, date(2019, 1, 1)) for c in ("11111111", "22222222", "33333333")],
        [
            ("before", "11111111000100", "11111111", "2025-10-31 23:59"),  # before the cutoff
            ("inside", "22222222000100", "22222222", "2026-04-15 10:00"),
            ("after", "33333333000100", "33333333", "2026-11-01 00:00"),  # horizon is exclusive
        ],
    )
    rows = by_id(build(conn, CUTOFF, END))
    assert {c: r["won"] for c, r in rows.items()} == {
        "11111111": False,
        "22222222": True,
        "33333333": False,
    }


def test_window_outside_the_loaded_contracts_fails(conn):
    with pytest.raises(ValueError, match="do not cover"):
        build(conn, CUTOFF, date(2027, 1, 1))
    with pytest.raises(ValueError, match="must be before"):
        build(conn, END, CUTOFF)
