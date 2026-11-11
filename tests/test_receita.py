from datetime import date
from decimal import Decimal

import pytest

from lode.etl import receita as R
from tests.fake_receita import write_zip


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20150310", date(2015, 3, 10)),
        ("", None),
        ("0", None),
        ("00000000", None),
        ("20151340", None),  # month 13
    ],
)
def test_parse_date(raw, expected):
    assert R.parse_date(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("15000,00", Decimal("15000.00")), ("1.500,50", Decimal("1500.50")), ("", Decimal(0))],
)
def test_parse_capital(raw, expected):
    assert R.parse_capital(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("JOAO DA SILVA 12345678901", "JOAO DA SILVA"),
        ("TECH 2000 SOLUCOES LTDA", "TECH 2000 SOLUCOES LTDA"),  # numbers that are not a CPF
        ("ACME LTDA", "ACME LTDA"),
    ],
)
def test_strip_cpf_removes_only_a_trailing_cpf(raw, expected):
    assert R.strip_cpf(raw) == expected


def test_phone_joins_ddd_and_number():
    assert R.phone("11", "33334444") == "1133334444"
    assert R.phone("", "") is None


def test_read_rows_streams_latin1_csv_from_zip(tmp_path):
    path = write_zip(tmp_path / "Cnaes.zip", [["6201501", "Desenvolvimento de programas"]])
    assert list(R.read_rows(path)) == [["6201501", "Desenvolvimento de programas"]]


def test_parts_finds_all_numbered_zips(tmp_path):
    for i in (1, 0):
        write_zip(tmp_path / f"Empresas{i}.zip", [])
    assert [p.name for p in R.parts(tmp_path, "Empresas")] == ["Empresas0.zip", "Empresas1.zip"]
    with pytest.raises(FileNotFoundError):
        R.parts(tmp_path, "Socios")
