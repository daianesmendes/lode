"""The Receita Federal CNPJ open data: file layouts and value parsing.

Each month the Receita publishes zip files with headerless CSVs (";" separator, Latin-1).
Files are split into parts (Estabelecimentos0.zip ... Estabelecimentos9.zip) and linked by
cnpj_basico, the first 8 digits of the CNPJ. Column order follows the official layout:
https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf
"""

import csv
import io
import re
import zipfile
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

# Column positions we use, per file family (0-based).
ESTABELECIMENTO = {
    "cnpj_basico": 0,
    "cnpj_ordem": 1,
    "cnpj_dv": 2,
    "matriz_filial": 3,  # 1 = headquarters, 2 = branch
    "nome_fantasia": 4,
    "situacao": 5,  # 02 = active
    "data_situacao": 6,
    "data_inicio": 10,
    "cnae_principal": 11,
    "cnae_secundaria": 12,  # comma-separated
    "tipo_logradouro": 13,
    "logradouro": 14,
    "numero": 15,
    "complemento": 16,
    "bairro": 17,
    "cep": 18,
    "uf": 19,
    "municipio": 20,  # Receita's own municipality code (not IBGE)
    "ddd1": 21,
    "telefone1": 22,
    "ddd2": 23,
    "telefone2": 24,
    "email": 27,
}
EMPRESA = {
    "cnpj_basico": 0,
    "razao_social": 1,
    "natureza_juridica": 2,
    "capital_social": 4,  # "1000,00"
    "porte": 5,  # 00 not informed, 01 micro, 03 small (EPP), 05 other
}
SIMPLES = {
    "cnpj_basico": 0,
    "opcao_simples": 1,  # S / N
    "data_opcao_simples": 2,
    "opcao_mei": 4,  # S / N
    "data_opcao_mei": 5,
}
SOCIO = {
    "cnpj_basico": 0,
    "tipo": 1,  # 1 = company, 2 = person, 3 = foreigner
    "data_entrada": 5,
    "faixa_etaria": 10,  # 1 = 0-12 ... 9 = over 80, 0 = not applicable
}

SITUACAO_ATIVA = "02"


def read_rows(path: Path) -> Iterator[list[str]]:
    """Stream the rows of the CSV inside a Receita zip, without extracting it to disk."""
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            with zf.open(name) as raw:
                text = io.TextIOWrapper(raw, encoding="latin-1", newline="")
                yield from csv.reader(text, delimiter=";", quotechar='"')


def parts(source: Path, family: str) -> list[Path]:
    """All zip parts of a file family, e.g. parts(dir, "Empresas") -> Empresas0..9.zip."""
    found = sorted(source.glob(f"{family}*.zip"))
    if not found:
        raise FileNotFoundError(f"no {family}*.zip in {source}")
    return found


def parse_date(value: str) -> date | None:
    """Receita dates are YYYYMMDD; empty or "0" means unknown."""
    value = value.strip()
    if len(value) != 8 or value == "00000000":
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def parse_capital(value: str) -> Decimal:
    """Capital social uses a comma as decimal separator: "15000,00" -> 15000.00."""
    value = value.strip().replace(".", "").replace(",", ".")
    return Decimal(value) if value else Decimal(0)


_TRAILING_CPF = re.compile(r"\s*\d{11}\s*$")


def strip_cpf(razao_social: str) -> str:
    """Remove the owner's CPF that individual businesses (MEI/EI) carry in their legal name.

    >>> strip_cpf("JOAO DA SILVA 12345678901")
    'JOAO DA SILVA'
    """
    return _TRAILING_CPF.sub("", razao_social).strip()


def phone(ddd: str, number: str) -> str | None:
    digits = "".join(ch for ch in ddd + number if ch.isdigit())
    return digits or None
