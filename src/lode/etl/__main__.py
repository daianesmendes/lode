"""Monthly load: uv run python -m lode.etl --month 2026-10 [--download]"""

import argparse
import os
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from lode.etl.download import available_months, download_month
from lode.etl.extract import extract, read_lookup
from lode.etl.load import load
from lode.sector import SOFTWARE


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Receita CNPJ open data into Postgres.")
    parser.add_argument("--month", help="YYYY-MM (default: latest published)")
    parser.add_argument("--data", type=Path, default=Path("data/raw"), help="download folder")
    parser.add_argument("--download", action="store_true", help="download missing files first")
    args = parser.parse_args()

    load_dotenv()
    month = args.month or available_months()[-1]
    source = download_month(month, args.data) if args.download else args.data / month

    started = time.monotonic()

    def progress(msg: str) -> None:
        print(f"[{time.monotonic() - started:6.0f}s] {msg}", flush=True)

    data = extract(source, SOFTWARE, progress)
    municipalities = read_lookup(source, "Municipios")
    cnaes = read_lookup(source, "Cnaes")

    progress("carregando no Postgres")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        result = load(conn, data, month, municipalities, cnaes)
    progress(f"pronto: {result}")


if __name__ == "__main__":
    main()
