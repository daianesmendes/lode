"""Extract the target companies from the Receita files.

Four passes, all streaming from the zips:
  1. Estabelecimentos -> active establishments of the sector in the target states.
     Their cnpj_basico set defines which companies we keep.
  2. Empresas         -> legal name, capital, size of those companies.
  3. Simples          -> Simples Nacional / MEI flags.
  4. Socios           -> partner counts only. No names are kept (LGPD).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from lode.etl import receita as R
from lode.sector import Sector

Progress = Callable[[str], None]


@dataclass
class Establishment:
    cnpj: str
    cnpj_basico: str
    is_headquarters: bool
    trade_name: str | None
    opened_on: date | None
    cnae_main: str
    cnaes_secondary: list[str]
    street: str | None
    district: str | None
    zip_code: str | None
    uf: str
    municipality_code: str
    phone1: str | None
    phone2: str | None
    email: str | None


@dataclass
class Company:
    cnpj_basico: str
    legal_name: str
    legal_nature: str
    capital: Decimal
    size_code: str
    is_simples: bool = False
    simples_since: date | None = None
    is_mei: bool = False
    mei_since: date | None = None
    partners: int = 0
    partners_person: int = 0
    partners_company: int = 0
    partners_foreign: int = 0
    youngest_age_band: int | None = None
    oldest_age_band: int | None = None
    first_partner_since: date | None = None


@dataclass
class Extraction:
    establishments: list[Establishment] = field(default_factory=list)
    companies: dict[str, Company] = field(default_factory=dict)
    rows_read: dict[str, int] = field(default_factory=dict)


def _clean(value: str) -> str | None:
    value = value.strip()
    return value or None


def parse_establishment(row: list[str], sector: Sector) -> Establishment | None:
    """Return the establishment if it is active, in a target state and in the sector."""
    c = R.ESTABELECIMENTO
    if row[c["situacao"]] != R.SITUACAO_ATIVA or row[c["uf"]] not in sector.states:
        return None
    if row[c["cnae_principal"]] not in sector.cnaes:
        return None
    street = " ".join(
        p for p in (row[c["tipo_logradouro"]], row[c["logradouro"]], row[c["numero"]]) if p.strip()
    )
    email = _clean(row[c["email"]])
    return Establishment(
        cnpj=row[c["cnpj_basico"]] + row[c["cnpj_ordem"]] + row[c["cnpj_dv"]],
        cnpj_basico=row[c["cnpj_basico"]],
        is_headquarters=row[c["matriz_filial"]] == "1",
        trade_name=_clean(row[c["nome_fantasia"]]),
        opened_on=R.parse_date(row[c["data_inicio"]]),
        cnae_main=row[c["cnae_principal"]],
        cnaes_secondary=[x for x in row[c["cnae_secundaria"]].split(",") if x.strip()],
        street=street or None,
        district=_clean(row[c["bairro"]]),
        zip_code=_clean(row[c["cep"]]),
        uf=row[c["uf"]],
        municipality_code=row[c["municipio"]],
        phone1=R.phone(row[c["ddd1"]], row[c["telefone1"]]),
        phone2=R.phone(row[c["ddd2"]], row[c["telefone2"]]),
        email=email.lower() if email else None,
    )


def parse_company(row: list[str]) -> Company:
    c = R.EMPRESA
    return Company(
        cnpj_basico=row[c["cnpj_basico"]],
        legal_name=R.strip_cpf(row[c["razao_social"]]),
        legal_nature=row[c["natureza_juridica"]],
        capital=R.parse_capital(row[c["capital_social"]]),
        size_code=row[c["porte"]],
    )


def apply_simples(company: Company, row: list[str]) -> None:
    c = R.SIMPLES
    company.is_simples = row[c["opcao_simples"]] == "S"
    company.simples_since = R.parse_date(row[c["data_opcao_simples"]])
    company.is_mei = row[c["opcao_mei"]] == "S"
    company.mei_since = R.parse_date(row[c["data_opcao_mei"]])


def add_partner(company: Company, row: list[str]) -> None:
    """Aggregate one partner row into counts. The partner's name and CPF are never stored."""
    c = R.SOCIO
    company.partners += 1
    kind = row[c["tipo"]]
    if kind == "1":
        company.partners_company += 1
    elif kind == "2":
        company.partners_person += 1
    elif kind == "3":
        company.partners_foreign += 1
    band = row[c["faixa_etaria"]].strip()
    if band.isdigit() and band != "0":
        b = int(band)
        company.youngest_age_band = min(company.youngest_age_band or b, b)
        company.oldest_age_band = max(company.oldest_age_band or b, b)
    since = R.parse_date(row[c["data_entrada"]])
    if since and (company.first_partner_since is None or since < company.first_partner_since):
        company.first_partner_since = since


def _scan(paths: Iterable[Path], label: str, out: Extraction, progress: Progress):
    count = 0
    for path in paths:
        progress(f"{label}: {path.name}")
        for row in R.read_rows(path):
            count += 1
            yield row
    out.rows_read[label] = count


def extract(source: Path, sector: Sector, progress: Progress = lambda _: None) -> Extraction:
    out = Extraction()

    for row in _scan(R.parts(source, "Estabelecimentos"), "estabelecimentos", out, progress):
        est = parse_establishment(row, sector)
        if est:
            out.establishments.append(est)
    wanted = {e.cnpj_basico for e in out.establishments}

    for row in _scan(R.parts(source, "Empresas"), "empresas", out, progress):
        if row[R.EMPRESA["cnpj_basico"]] in wanted:
            company = parse_company(row)
            out.companies[company.cnpj_basico] = company

    for row in _scan(R.parts(source, "Simples"), "simples", out, progress):
        company = out.companies.get(row[R.SIMPLES["cnpj_basico"]])
        if company:
            apply_simples(company, row)

    for row in _scan(R.parts(source, "Socios"), "socios", out, progress):
        company = out.companies.get(row[R.SOCIO["cnpj_basico"]])
        if company:
            add_partner(company, row)

    return out


def read_lookup(source: Path, family: str) -> dict[str, str]:
    """Small code -> description tables (Municipios, Cnaes, Naturezas)."""
    return {row[0]: row[1] for path in R.parts(source, family) for row in R.read_rows(path)}
