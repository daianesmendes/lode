"""Load an Extraction into Postgres, replacing the previous month in one transaction."""

import json
from datetime import date, datetime
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


CONTRACT_COLUMNS = (
    "id cnpj cnpj_basico object value signed_on valid_from valid_to published_at contract_type "
    "category buyer_cnpj buyer_name buyer_sphere buyer_uf buyer_ibge"
).split()


def _iso(value, kind=date):
    """PNCP dates are ISO strings; malformed ones become NULL instead of failing the load."""
    if not value:
        return None
    try:
        return kind.fromisoformat(str(value)[: 10 if kind is date else 19])
    except ValueError:
        return None


def contract_row(c: dict) -> list:
    return [
        c["id"],
        c["supplier_id"],
        c["supplier_id"][:8],
        c.get("object"),
        c.get("value"),
        _iso(c.get("signed_on")),
        _iso(c.get("valid_from")),
        _iso(c.get("valid_to")),
        _iso(c.get("published_at"), datetime),
        c.get("contract_type"),
        c.get("category"),
        c.get("buyer_cnpj"),
        c.get("buyer_name"),
        c.get("buyer_sphere"),
        c.get("buyer_uf"),
        str(c["buyer_ibge"]) if c.get("buyer_ibge") else None,
    ]


def company_ids(conn: psycopg.Connection) -> set[str]:
    return {row[0] for row in conn.execute("select cnpj_basico from company")}


def load_contracts(
    conn: psycopg.Connection, contracts: list[dict], start: date, end: date, read: int
) -> dict[str, int]:
    """Replace the public contracts with the ones of the given period."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(SCHEMA.read_text())
        cur.execute("truncate public_contract, pncp_info")
        _copy(cur, "public_contract", CONTRACT_COLUMNS, (contract_row(c) for c in contracts))
        cur.execute(
            "insert into pncp_info (period_start, period_end, contracts_read, contracts_kept) "
            "values (%s, %s, %s, %s)",
            (start, end, read, len(contracts)),
        )
    return {"contracts_read": read, "contracts_kept": len(contracts)}
