from dataclasses import asdict

import pytest

from lode.etl.extract import extract
from lode.sector import SOFTWARE
from tests import fake_receita as F


@pytest.fixture
def month(tmp_path):
    """A fake month with one company that matches and several that must be filtered out."""
    F.write_zip(
        tmp_path / "Estabelecimentos0.zip",
        [
            F.estabelecimento("11111111", nome_fantasia="ACME", email="Contato@Acme.com"),
            F.estabelecimento("11111111", matriz="2"),  # branch of the same company
            F.estabelecimento("22222222", situacao="08"),  # closed
            F.estabelecimento("33333333", uf="RJ"),  # other state
            # IT only as a secondary activity
            F.estabelecimento("44444444", cnae="4120400", secundarias="6201501"),
            F.estabelecimento("55555555", cnae="6204000"),  # MEI consultant
        ],
    )
    F.write_zip(
        tmp_path / "Empresas0.zip",
        [
            F.empresa("11111111"),
            F.empresa("22222222"),
            F.empresa("55555555", razao="MARIA SOUZA 12345678901", capital="1000,00"),
        ],
    )
    F.write_zip(tmp_path / "Simples.zip", [F.simples("11111111"), F.simples("55555555", mei="S")])
    F.write_zip(
        tmp_path / "Socios0.zip",
        [
            F.socio("11111111", tipo="2", faixa="4", entrada="20150310"),
            F.socio("11111111", tipo="2", faixa="6", entrada="20190101"),
            F.socio("11111111", tipo="1", faixa="0", nome="HOLDING SA"),
            F.socio("99999999"),  # partner of a company we don't keep
        ],
    )
    return tmp_path


def test_keeps_only_active_sector_establishments_in_target_state(month):
    data = extract(month, SOFTWARE)
    kept = sorted(e.cnpj_basico for e in data.establishments)
    assert kept == ["11111111", "11111111", "55555555"]
    assert sorted(data.companies) == ["11111111", "55555555"]


def test_establishment_fields(month):
    hq = next(e for e in extract(month, SOFTWARE).establishments if e.is_headquarters)
    assert hq.cnpj == "11111111000199"
    assert hq.trade_name == "ACME"
    assert hq.email == "contato@acme.com"
    assert hq.street == "RUA DAS FLORES 100"
    assert hq.phone1 == "1133334444"


def test_mei_flag_and_cpf_removed_from_name(month):
    mei = extract(month, SOFTWARE).companies["55555555"]
    assert mei.is_mei and mei.is_simples
    assert mei.legal_name == "MARIA SOUZA"


def test_partners_are_aggregated_without_personal_data(month):
    acme = extract(month, SOFTWARE).companies["11111111"]
    assert (acme.partners, acme.partners_person, acme.partners_company) == (3, 2, 1)
    assert (acme.youngest_age_band, acme.oldest_age_band) == (4, 6)
    assert acme.first_partner_since.isoformat() == "2015-03-10"
    stored = str(asdict(acme))
    assert "FULANO" not in stored and "123456" not in stored


def test_counts_rows_read_per_family(month):
    assert extract(month, SOFTWARE).rows_read == {
        "estabelecimentos": 6,
        "empresas": 3,
        "simples": 2,
        "socios": 4,
    }
