"""ETL commands.

uv run python -m lode.etl receita --month 2026-10 [--download]
uv run python -m lode.etl pncp --start 2025-11-01 --end 2026-10-31 [--download]
"""

import argparse
import os
import time
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from lode.etl import pncp
from lode.etl.download import available_months, download_month
from lode.etl.extract import extract, read_lookup
from lode.etl.load import company_ids, load, load_contracts
from lode.sector import SOFTWARE

_started = time.monotonic()


def progress(msg: str) -> None:
    print(f"[{time.monotonic() - _started:6.0f}s] {msg}", flush=True)


def run_receita(args: argparse.Namespace) -> None:
    month = args.month or available_months()[-1]
    source = download_month(month, args.data) if args.download else args.data / month
    data = extract(source, SOFTWARE, progress)
    municipalities = read_lookup(source, "Municipios")
    cnaes = read_lookup(source, "Cnaes")
    progress("carregando no Postgres")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        result = load(conn, data, month, municipalities, cnaes)
    progress(f"pronto: {result}")


def run_pncp(args: argparse.Namespace) -> None:
    if args.download and pncp.download(args.start, args.end, args.cache, log=progress):
        raise SystemExit("some days are still missing: run again before loading")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        companies = company_ids(conn)
        if not companies:
            raise SystemExit("no companies loaded yet: run the receita load first")
        read = 0

        def counted():
            nonlocal read
            for contract in pncp.read_cache(args.cache, args.start, args.end):
                read += 1
                yield contract

        kept = pncp.contracts_of(companies, counted())
        progress(f"carregando {len(kept):,} contratos no Postgres")
        result = load_contracts(conn, kept, args.start, args.end, read)
    progress(f"pronto: {result}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="lode.etl", description="Lode data loads.")
    sub = parser.add_subparsers(dest="command", required=True)

    receita = sub.add_parser("receita", help="Receita Federal CNPJ open data")
    receita.add_argument("--month", help="YYYY-MM (default: latest published)")
    receita.add_argument("--data", type=Path, default=Path("data/raw"))
    receita.add_argument("--download", action="store_true", help="download missing files first")
    receita.set_defaults(run=run_receita)

    contracts = sub.add_parser("pncp", help="public contracts (PNCP)")
    contracts.add_argument("--start", type=date.fromisoformat, required=True)
    contracts.add_argument("--end", type=date.fromisoformat, required=True)
    contracts.add_argument("--cache", type=Path, default=Path("data/pncp"))
    contracts.add_argument("--download", action="store_true", help="download missing days first")
    contracts.set_defaults(run=run_pncp)

    args = parser.parse_args()
    load_dotenv()
    args.run(args)


if __name__ == "__main__":
    main()
