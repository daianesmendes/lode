"""Tiny Receita-format zip files for tests (headerless, ';'-separated, Latin-1)."""

import csv
import io
import zipfile
from pathlib import Path


def write_zip(path: Path, rows: list[list[str]]) -> Path:
    buf = io.StringIO()
    csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(path.stem.upper() + ".CSV", buf.getvalue().encode("latin-1"))
    return path


def estabelecimento(cnpj_basico, *, uf="SP", situacao="02", cnae="6201501", matriz="1", **kw):
    row = [""] * 30
    ordem = "0001" if matriz == "1" else "0002"
    row[0], row[1], row[2], row[3] = cnpj_basico, ordem, "99", matriz
    row[4] = kw.get("nome_fantasia", "")
    row[5], row[10], row[11], row[12] = situacao, "20150310", cnae, kw.get("secundarias", "")
    row[13], row[14], row[15] = "RUA", "DAS FLORES", "100"
    row[17], row[18], row[19], row[20] = "CENTRO", "01001000", uf, "7107"
    row[21], row[22], row[27] = "11", "33334444", kw.get("email", "")
    return row


def empresa(cnpj_basico, razao="ACME SOFTWARE LTDA", capital="50000,00", porte="01"):
    return [cnpj_basico, razao, "2062", "49", capital, porte, ""]


def simples(cnpj_basico, mei="N"):
    return [cnpj_basico, "S", "20180101", "", mei, "20180101" if mei == "S" else "", ""]


def socio(cnpj_basico, tipo="2", faixa="4", entrada="20150310", nome="FULANO DE TAL"):
    return [cnpj_basico, tipo, nome, "***123456**", "49", entrada, "", "", "", "", faixa]
