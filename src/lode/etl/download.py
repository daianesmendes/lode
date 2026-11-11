"""Download a month of Receita CNPJ open data.

The files are served by a Nextcloud public share over WebDAV. The share token below is public
(it is published by the Receita through the dados.gov.br catalog) and works as the username.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import httpx

BASE_URL = "https://arquivos.receitafederal.gov.br/public.php/webdav/"
SHARE_TOKEN = "YggdBLfdninEJX9"
_DAV = "{DAV:}"


@dataclass(frozen=True)
class RemoteFile:
    name: str
    size: int


def parse_listing(xml: str) -> list[RemoteFile]:
    """Files (not folders) in a WebDAV PROPFIND response."""
    files = []
    for response in ET.fromstring(xml).iter(f"{_DAV}response"):
        href = response.findtext(f"{_DAV}href", "")
        size = response.findtext(f".//{_DAV}getcontentlength")
        if size is not None and not href.endswith("/"):
            files.append(RemoteFile(name=href.rstrip("/").split("/")[-1], size=int(size)))
    return files


def _client() -> httpx.Client:
    return httpx.Client(auth=(SHARE_TOKEN, ""), timeout=httpx.Timeout(60, read=300))


def available_months(client: httpx.Client | None = None) -> list[str]:
    client = client or _client()
    xml = client.request("PROPFIND", BASE_URL, headers={"Depth": "1"}).text
    return sorted(re.findall(r"/webdav/(\d{4}-\d{2})/", xml))


def list_month(month: str, client: httpx.Client | None = None) -> list[RemoteFile]:
    client = client or _client()
    response = client.request("PROPFIND", f"{BASE_URL}{month}/", headers={"Depth": "1"})
    response.raise_for_status()
    return parse_listing(response.text)


def download_month(month: str, dest: Path, log=print) -> Path:
    """Download every zip of the month into dest/<month>/, skipping files already complete."""
    folder = dest / month
    folder.mkdir(parents=True, exist_ok=True)
    with _client() as client:
        for remote in list_month(month, client):
            target = folder / remote.name
            if target.exists() and target.stat().st_size == remote.size:
                log(f"ok      {remote.name}")
                continue
            log(f"baixando {remote.name} ({remote.size / 1e6:,.0f} MB)")
            partial = target.with_suffix(target.suffix + ".part")
            with client.stream("GET", f"{BASE_URL}{month}/{remote.name}") as response:
                response.raise_for_status()
                with partial.open("wb") as fh:
                    for chunk in response.iter_bytes(1 << 20):
                        fh.write(chunk)
            partial.rename(target)
    return folder
