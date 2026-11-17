import os

import psycopg
import pytest

from lode.etl.load import SCHEMA
from lode.site.candidates import candidates

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


def test_candidates_use_the_headquarters_domain_and_count_sharing():
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text())
        conn.execute(
            "truncate company_score, public_contract, establishment, company, municipality, "
            "municipality_ibge"
        )
        # A: own domain on its headquarters, a gmail on a branch.
        # B and C: both registered with their accountant's e-mail. D: gmail only.
        emails = {
            "11111111": [(True, "contato@alfa.com.br"), (False, "filial@gmail.com")],
            "22222222": [(True, "fiscal@contabil.com.br")],
            "33333333": [(True, "cliente33@contabil.com.br")],
            "44444444": [(True, "dono@gmail.com")],
        }
        for rank, (cnpj, mails) in enumerate(emails.items(), start=1):
            conn.execute(
                "insert into company (cnpj_basico, legal_name, legal_nature, capital, "
                "size_code, is_simples, is_mei, partners, partners_person, partners_company, "
                "partners_foreign) values (%s, %s, '2062', 1, '01', false, false, 1, 1, 0, 0)",
                (cnpj, f"COMPANY {cnpj}"),
            )
            for branch, (hq, email) in enumerate(mails, start=1):
                conn.execute(
                    "insert into establishment (cnpj, cnpj_basico, is_headquarters, cnae_main, "
                    "cnaes_secondary, uf, municipality_code, email) "
                    "values (%s, %s, %s, '6201501', '{}', 'SP', '7107', %s)",
                    (f"{cnpj}{branch:04d}00", cnpj, hq, email),
                )
            conn.execute(
                "insert into company_score (cnpj_basico, score, rank, municipality_code) "
                "values (%s, 0.5, %s, '7107')",
                (cnpj, rank),
            )
        found = {c.cnpj_basico: (c.domain, c.shared_by) for c in candidates(conn, top=10)}
        assert found == {
            "11111111": ("alfa.com.br", 1),
            "22222222": ("contabil.com.br", 2),
            "33333333": ("contabil.com.br", 2),
        }
        assert [c.cnpj_basico for c in candidates(conn, top=2)] == ["11111111", "22222222"]
