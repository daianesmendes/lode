"""Load an Extraction into Postgres, replacing the previous month in one transaction."""

import json
from pathlib import Path

import psycopg

from lode.etl.extract import Extraction

SCHEMA = Path(__file__).resolve().parents[3] / "sql" / "schema.sql"

COMPANY_COLUMNS = (
    "cnpj_basico legal_name legal_nature capital size_code is_simples simples_since is_mei "
    "mei_since partners partners_person partners_company partners_foreign youngest_age_band "
    "oldest_age_band first_partner_since"
).split()
ESTABLISHMENT_COLUMNS = (
    "cnpj cnpj_basico is_headquarters trade_name opened_on cnae_main cnaes_secondary street "
    "district zip_code uf municipality_code phone1 phone2 email"
).split()


def _copy(cur: psycopg.Cursor, table: str, columns: list[str], rows) -> None:
    with cur.copy(f"copy {table} ({', '.join(columns)}) from stdin") as copy:
        for row in rows:
            copy.write_row(row)


def load(
    conn: psycopg.Connection,
    data: Extraction,
    month: str,
    municipalities: dict[str, str],
    cnaes: dict[str, str],
) -> dict[str, int]:
    # An establishment whose company is missing from Empresas would break the foreign key.
    establishments = [e for e in data.establishments if e.cnpj_basico in data.companies]
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(SCHEMA.read_text())
        cur.execute("truncate establishment, company, municipality, cnae, load_info")
        _copy(
            cur,
            "company",
            COMPANY_COLUMNS,
            ([getattr(c, col) for col in COMPANY_COLUMNS] for c in data.companies.values()),
        )
        _copy(
            cur,
            "establishment",
            ESTABLISHMENT_COLUMNS,
            ([getattr(e, col) for col in ESTABLISHMENT_COLUMNS] for e in establishments),
        )
        _copy(cur, "municipality", ["code", "name"], municipalities.items())
        _copy(cur, "cnae", ["code", "description"], cnaes.items())
        cur.execute(
            "insert into load_info (month, companies, establishments, rows_read) "
            "values (%s, %s, %s, %s)",
            (month, len(data.companies), len(establishments), json.dumps(data.rows_read)),
        )
    return {
        "companies": len(data.companies),
        "establishments": len(establishments),
        "establishments_without_company": len(data.establishments) - len(establishments),
    }
