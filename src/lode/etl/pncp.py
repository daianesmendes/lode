"""Public contracts from the PNCP (Portal Nacional de Contratações Públicas).

The consultation API only filters by publication date, so we download every contract of each
day and keep a slim copy on disk (one gzipped JSON-lines file per day). Downloads resume from
the first missing day, and the cache can be filtered again if the target companies change.
API docs: https://pncp.gov.br/api/consulta/swagger-ui/index.html
"""

import gzip
import json
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import httpx

API_URL = "https://pncp.gov.br/api/consulta/v1/contratos"
PAGE_SIZE = 500  # the API maximum
RETRY_STATUS = {429, 500, 502, 503, 504}


def slim(record: dict) -> dict:
    """Keep only the fields Lode uses."""
    organ = record.get("orgaoEntidade") or {}
    unit = record.get("unidadeOrgao") or {}
    return {
        "id": record["numeroControlePNCP"],
        "supplier_type": record.get("tipoPessoa"),
        "supplier_id": record.get("niFornecedor"),
        "object": record.get("objetoContrato"),
        "value": record.get("valorGlobal"),
        "signed_on": record.get("dataAssinatura"),
        "valid_from": record.get("dataVigenciaInicio"),
        "valid_to": record.get("dataVigenciaFim"),
        "published_at": record.get("dataPublicacaoPncp"),
        "updated_at": record.get("dataAtualizacaoGlobal") or record.get("dataAtualizacao"),
        "contract_type": (record.get("tipoContrato") or {}).get("nome"),
        "category": (record.get("categoriaProcesso") or {}).get("nome"),
        "buyer_cnpj": organ.get("cnpj"),
        "buyer_name": organ.get("razaoSocial"),
        "buyer_sphere": organ.get("esferaId"),  # F federal, E state, M municipal, D district
        "buyer_uf": unit.get("ufSigla"),
        "buyer_ibge": unit.get("codigoIbge"),
    }


def get_page(client: httpx.Client, day: date, page: int, attempts: int = 6) -> dict:
    """One page of contracts published on `day`, retrying the API's frequent failures."""
    params = {
        "dataInicial": day.strftime("%Y%m%d"),
        "dataFinal": day.strftime("%Y%m%d"),
        "pagina": page,
        "tamanhoPagina": PAGE_SIZE,
    }
    for attempt in range(attempts):
        try:
            response = client.get(API_URL, params=params)
            if response.status_code == 204:  # no contracts that day
                return {"data": [], "totalPaginas": 0}
            if response.status_code not in RETRY_STATUS:
                response.raise_for_status()
                return response.json()
        except (httpx.TimeoutException, httpx.TransportError):
            pass
        if attempt < attempts - 1:
            time.sleep(min(2**attempt, 60))
    raise RuntimeError(f"PNCP failed for {day} page {page} after {attempts} attempts")


def fetch_day(client: httpx.Client, day: date) -> list[dict]:
    first = get_page(client, day, 1)
    records = list(first.get("data") or [])
    for page in range(2, (first.get("totalPaginas") or 0) + 1):
        records.extend(get_page(client, day, page).get("data") or [])
    return [slim(r) for r in records]


def day_file(cache: Path, day: date) -> Path:
    return cache / f"{day.isoformat()}.jsonl.gz"


def download(
    start: date,
    end: date,
    cache: Path,
    workers: int = 4,
    log: Callable[[str], None] = print,
    client: httpx.Client | None = None,
) -> None:
    """Download every day in [start, end] that is not cached yet."""
    cache.mkdir(parents=True, exist_ok=True)
    days = [start + timedelta(n) for n in range((end - start).days + 1)]
    missing = [d for d in days if not day_file(cache, d).exists()]
    log(f"{len(days) - len(missing)} dias já baixados, {len(missing)} faltando")
    client = client or httpx.Client(timeout=httpx.Timeout(30, read=120))

    def one(day: date) -> str:
        contracts = fetch_day(client, day)
        target = day_file(cache, day)
        partial = target.with_suffix(".part")
        with gzip.open(partial, "wt", encoding="utf-8") as fh:
            for c in contracts:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        partial.rename(target)  # a day only counts as done once fully written
        return f"{day}: {len(contracts):,} contratos"

    with ThreadPoolExecutor(workers) as pool:
        for n, message in enumerate(pool.map(one, missing), 1):
            log(f"[{n}/{len(missing)}] {message}")


def read_cache(cache: Path, start: date, end: date) -> Iterator[dict]:
    day = start
    while day <= end:
        path = day_file(cache, day)
        if not path.exists():
            raise FileNotFoundError(f"day {day} not downloaded; run the download first")
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                yield json.loads(line)
        day += timedelta(1)


def contracts_of(companies: set[str], contracts: Iterable[dict]) -> list[dict]:
    """Contracts whose supplier is one of our companies, one row per contract (latest version)."""
    latest: dict[str, dict] = {}
    for c in contracts:
        supplier = c.get("supplier_id") or ""
        if c.get("supplier_type") != "PJ" or len(supplier) != 14:
            continue
        if supplier[:8] not in companies:
            continue
        kept = latest.get(c["id"])
        if kept is None or (c.get("updated_at") or "") >= (kept.get("updated_at") or ""):
            latest[c["id"]] = c
    return list(latest.values())
