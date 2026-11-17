"""City codes for the map: Receita code -> IBGE code, and the city outlines.

The Receita identifies cities by the old SIAFI/TOM code ("7107" for São Paulo), while maps use
the IBGE code ("3550308"). Matching them by name breaks on spelling ("SAO LUIZ DO PARAITINGA"
vs "São Luís do Paraitinga"), so the official table that holds both codes is used instead: the
National Treasury's CAUC report, published as open data (ODbL).

The outlines come from the IBGE mesh API, at its lightest quality, and are saved as a static
GeoJSON file for the web app.
"""

import csv
import io
import json
from pathlib import Path

import httpx
import psycopg

from lode.etl.load import SCHEMA

CAUC_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/72b5f371-0c35-4613-8076-c99c821a6410/"
    "resource/07af297a-5e59-494a-a88a-55ddfd2f4b01/download/"
    "relatorio-situacao-de-varios-entes---municipios---uf-todas---abrangencia-1.csv"
)
MESH_URL = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{state}"
STATE_IBGE = {  # first two digits of every IBGE city code of the state
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17",
    "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27",
    "SE": "28", "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35", "PR": "41",
    "SC": "42", "RS": "43", "MS": "50", "MT": "51", "GO": "52", "DF": "53",
}  # fmt: skip


def parse_cauc(text: str, states: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    """Receita/SIAFI code -> (IBGE code, official name), for the cities of `states`."""
    lines = text.splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith('"UF";'))
    rows = csv.DictReader(io.StringIO("\n".join(lines[header:])), delimiter=";")
    return {
        row["Código SIAFI"]: (row["Código IBGE"], row["Nome do Ente Federado"])
        for row in rows
        if row["UF"] in states
    }


def download_cauc(client: httpx.Client) -> str:
    response = client.get(CAUC_URL)
    response.raise_for_status()
    return response.content.decode("latin-1")


def load_codes(conn: psycopg.Connection, codes: dict[str, tuple[str, str]]) -> list[str]:
    """Replace the code table. Returns the Receita codes in use that got no IBGE code."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(SCHEMA.read_text())
        cur.execute("truncate municipality_ibge")
        with cur.copy("copy municipality_ibge (code, ibge_code, name) from stdin") as copy:
            for code, (ibge, name) in codes.items():
                copy.write_row((code, ibge, name))
    missing = conn.execute(
        "select distinct municipality_code from establishment "
        "where municipality_code not in (select code from municipality_ibge) order by 1"
    )
    return [row[0] for row in missing]


def simplify(geojson: dict, decimals: int = 4) -> dict:
    """Keep only the IBGE code and round coordinates (4 decimals is about 11 m)."""

    def rounded(coords):
        if isinstance(coords[0], (int, float)):
            return [round(c, decimals) for c in coords]
        return [rounded(c) for c in coords]

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"ibge_code": f["properties"]["codarea"]},
                "geometry": {
                    "type": f["geometry"]["type"],
                    "coordinates": rounded(f["geometry"]["coordinates"]),
                },
            }
            for f in geojson["features"]
        ],
    }


def download_outlines(client: httpx.Client, state: str) -> dict:
    params = {
        "formato": "application/vnd.geo+json",
        "qualidade": "minima",
        "intrarregiao": "municipio",
    }
    response = client.get(MESH_URL.format(state=STATE_IBGE[state]), params=params)
    response.raise_for_status()
    return simplify(response.json())


def save_outlines(outlines: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(outlines, separators=(",", ":")))
