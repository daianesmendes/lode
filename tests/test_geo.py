import os

import psycopg
import pytest

from lode.etl.geo import load_codes, parse_cauc, simplify
from lode.etl.load import SCHEMA

# Same layout as the Treasury file: a few report lines, then the table, decoded from latin-1.
CAUC = """"Data da Pesquisa: 17/11/2026"
"Tipo de Ente: Municípios"
"Abrangência: CNPJ principal dos Entes Federados"
"UF";"Nome do Ente Federado";"Código IBGE";"Código SIAFI";"Região";"População"
"RJ";"Niterói";"3303302";"5865";"SE";"481749"
"SP";"São Luís do Paraitinga";"3550001";"7095";"SE";"10397"
"SP";"São Paulo";"3550308";"7107";"SE";"11451245"
"""


def test_parse_cauc_keeps_the_target_states():
    assert parse_cauc(CAUC, ("SP",)) == {
        "7095": ("3550001", "São Luís do Paraitinga"),
        "7107": ("3550308", "São Paulo"),
    }


def test_simplify_rounds_and_keeps_only_the_code():
    mesh = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"codarea": "3550308", "other": 1},
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[[[-46.123456, -23.987654], [-46.2, -23.9], [-46.1, -23.8]]]],
                },
            }
        ],
    }
    feature = simplify(mesh)["features"][0]
    assert feature["properties"] == {"ibge_code": "3550308"}
    assert feature["geometry"]["coordinates"][0][0][0] == [-46.1235, -23.9877]


URL = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
def test_load_codes_reports_cities_left_without_ibge_code():
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text())
        conn.execute("truncate public_contract, establishment, company")
        conn.execute(
            "insert into company (cnpj_basico, legal_name, legal_nature, capital, size_code, "
            "is_simples, is_mei, partners, partners_person, partners_company, partners_foreign) "
            "values ('11111111', 'A', '2062', 1, '01', false, false, 0, 0, 0, 0)"
        )
        conn.execute(
            "insert into establishment (cnpj, cnpj_basico, is_headquarters, cnae_main, "
            "cnaes_secondary, uf, municipality_code) values "
            "('11111111000100', '11111111', true, '6201501', '{}', 'SP', '7107'), "
            "('11111111000200', '11111111', false, '6201501', '{}', 'SP', '9999')"
        )
        assert load_codes(conn, parse_cauc(CAUC, ("SP",))) == ["9999"]
        assert conn.execute(
            "select ibge_code, name from municipality_ibge where code = '7095'"
        ).fetchone() == ("3550001", "São Luís do Paraitinga")
