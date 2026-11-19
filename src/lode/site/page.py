"""Download a site's home page and keep only its visible text.

Everything here is untrusted input from the open web: the size and the time are capped, only
HTML is read, and the text is later handed to the LLM as data, never as instructions.
"""

import json
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path

import httpx

MAX_BYTES = 500_000
MAX_CHARS = 6_000  # what the LLM gets: enough for a home page, cheap enough for a free tier
SKIP = {"script", "style", "noscript", "svg", "template", "head"}
USER_AGENT = "Mozilla/5.0 (compatible; Lode/0.1; public data research)"


@dataclass
class Page:
    domain: str
    url: str | None  # final URL after redirects; None when nothing answered
    status: int | None
    title: str
    text: str
    error: str | None = None


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            a = dict(attrs)
            if a.get("name", "").lower() == "description" and a.get("content"):
                self.parts.append(a["content"])

    def handle_endtag(self, tag):
        if tag in SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and data.strip():
            self.parts.append(data.strip())


# What a bot wall says instead of the site. Only the beginning of the page is checked, so a long
# page that merely mentions "access denied" somewhere is still readable.
BLOCK_SIGNS = (
    "403 forbidden", "403 - forbidden", "access to this page is forbidden", "access denied",
    "you have been blocked", "attention required", "security checkpoint",
    "verifying you are human", "verify you are human", "checking your browser", "just a moment",
    "enable javascript and cookies",
)  # fmt: skip


def blocked(page: "Page") -> bool:
    start = f"{page.title} {page.text[:600]}".lower()
    return any(sign in start for sign in BLOCK_SIGNS)


def readable(page: "Page") -> bool:
    """Whether there is anything to judge: the page answered, has text and is not a bot wall."""
    return bool(page.url and page.text) and not blocked(page)


def visible_text(html: str) -> tuple[str, str]:
    """(title, text) of an HTML page: no scripts or styles, whitespace collapsed."""
    parser = _Text()
    parser.feed(html)
    text = " ".join(" ".join(parser.parts).split())
    return " ".join(parser.title.split()), text[:MAX_CHARS]


def fetch(client: httpx.Client, domain: str) -> Page:
    """Try https://domain, https://www.domain, then plain http; first HTML answer wins."""
    error = None
    for url in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
        try:
            with client.stream("GET", url) as response:
                kind = response.headers.get("content-type", "")
                if "html" not in kind:
                    error = f"not html: {kind or 'no content type'}"
                    continue
                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        break
                encoding = response.encoding or "utf-8"
                title, text = visible_text(body.decode(encoding, errors="replace"))
                return Page(domain, str(response.url), response.status_code, title, text)
        except httpx.HTTPError as exc:
            error = type(exc).__name__
    return Page(domain, None, None, "", "", error)


def client() -> httpx.Client:
    return httpx.Client(
        timeout=10, follow_redirects=True, max_redirects=5, headers={"User-Agent": USER_AGENT}
    )


def cached(cache: Path, http: httpx.Client, domain: str) -> Page:
    """Fetch once per domain; later runs (labeling, evaluation) read the same page."""
    path = cache / f"{domain}.json"
    if path.exists():
        return Page(**json.loads(path.read_text()))
    page = fetch(http, domain)
    cache.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(page), ensure_ascii=False))
    return page
