from datetime import date

import httpx
import pytest

from lode.etl import pncp


def record(n, supplier="11111111000199", updated="2026-10-01T10:00:00", tipo="PJ"):
    return {
        "numeroControlePNCP": f"00000000000100-2-{n:06d}/2026",
        "tipoPessoa": tipo,
        "niFornecedor": supplier,
        "objetoContrato": "Licença de software",
        "valorGlobal": 1000.0,
        "dataAssinatura": "2026-09-30",
        "dataAtualizacaoGlobal": updated,
        "orgaoEntidade": {"cnpj": "00000000000100", "razaoSocial": "MUNICIPIO X", "esferaId": "M"},
        "unidadeOrgao": {"ufSigla": "SP", "codigoIbge": "3550308"},
        "tipoContrato": {"nome": "Contrato (termo inicial)"},
    }


def fake_api(pages_by_day, fail_first=0):
    """MockTransport serving pages per day; the first `fail_first` calls answer 503."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= fail_first:
            return httpx.Response(503)
        day = request.url.params["dataInicial"]
        pages = pages_by_day.get(day, [])
        if not pages:
            return httpx.Response(204)
        page = int(request.url.params["pagina"])
        return httpx.Response(200, json={"data": pages[page - 1], "totalPaginas": len(pages)})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(pncp.time, "sleep", lambda _: None)


def test_slim_keeps_the_fields_we_use():
    c = pncp.slim(record(1))
    assert c["supplier_id"] == "11111111000199"
    assert c["buyer_sphere"] == "M" and c["buyer_uf"] == "SP"
    assert c["contract_type"] == "Contrato (termo inicial)"


def test_fetch_day_reads_every_page():
    client, _ = fake_api({"20261001": [[record(1), record(2)], [record(3)]]})
    assert len(pncp.fetch_day(client, date(2026, 10, 1))) == 3


def test_get_page_retries_temporary_errors():
    client, calls = fake_api({"20261001": [[record(1)]]}, fail_first=2)
    assert len(pncp.get_page(client, date(2026, 10, 1), 1)["data"]) == 1
    assert calls["n"] == 3


def test_get_page_gives_up_after_the_last_attempt():
    client, _ = fake_api({}, fail_first=99)
    with pytest.raises(RuntimeError):
        pncp.get_page(client, date(2026, 10, 1), 1, attempts=3)


def test_download_caches_each_day_and_resumes(tmp_path):
    client, calls = fake_api({"20261001": [[record(1)]], "20261003": [[record(2), record(3)]]})
    pncp.download(date(2026, 10, 1), date(2026, 10, 3), tmp_path, log=lambda _: None, client=client)
    assert len(list(tmp_path.glob("*.jsonl.gz"))) == 3  # an empty day is cached too
    rows = list(pncp.read_cache(tmp_path, date(2026, 10, 1), date(2026, 10, 3)))
    assert len(rows) == 3

    before = calls["n"]
    pncp.download(date(2026, 10, 1), date(2026, 10, 3), tmp_path, log=lambda _: None, client=client)
    assert calls["n"] == before  # nothing downloaded twice


def test_read_cache_refuses_missing_days(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(pncp.read_cache(tmp_path, date(2026, 10, 1), date(2026, 10, 1)))


def test_contracts_of_filters_suppliers_and_keeps_latest_version():
    rows = [
        pncp.slim(record(1, updated="2026-10-01T10:00:00")),
        pncp.slim(record(1, updated="2026-10-05T10:00:00")),  # rectified later
        pncp.slim(record(2, supplier="99999999000199")),  # not our company
        pncp.slim(record(3, supplier="12345678901", tipo="PF")),  # a person
    ]
    kept = pncp.contracts_of({"11111111"}, rows)
    assert [c["updated_at"] for c in kept] == ["2026-10-05T10:00:00"]
