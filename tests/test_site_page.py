import httpx

from lode.site.candidates import usable
from lode.site.page import MAX_CHARS, cached, fetch, visible_text

HTML = """<html><head><title> Alfa  Sistemas </title>
<meta name="description" content="Software for city halls">
<style>body { color: red }</style><script>alert('x')</script></head>
<body><nav>Home</nav><h1>We build   ERP</h1><noscript>enable js</noscript><p>Since 1998.</p></body>
</html>"""


def test_visible_text_keeps_what_a_person_reads():
    title, text = visible_text(HTML)
    assert title == "Alfa Sistemas"
    assert text == "Software for city halls Home We build ERP Since 1998."


def test_visible_text_is_capped():
    _, text = visible_text("<p>" + "word " * 5000 + "</p>")
    assert len(text) == MAX_CHARS


def serve(routes):
    def handler(request):
        answer = routes.get(str(request.url).rstrip("/"))
        if answer is None:
            raise httpx.ConnectError("refused", request=request)
        status, kind, body = answer
        return httpx.Response(status, headers={"content-type": kind}, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_fetch_falls_back_to_www():
    client = serve({"https://www.alfa.com.br": (200, "text/html; charset=utf-8", HTML)})
    page = fetch(client, "alfa.com.br")
    assert page.url == "https://www.alfa.com.br" and page.title == "Alfa Sistemas"
    assert page.error is None


def test_fetch_ignores_what_is_not_html():
    client = serve({"https://alfa.com.br": (200, "application/pdf", "%PDF")})
    page = fetch(client, "alfa.com.br")
    assert page.url is None and page.error.startswith("ConnectError")


def test_nothing_answers():
    page = fetch(serve({}), "gone.com.br")
    assert (page.url, page.text, page.error) == (None, "", "ConnectError")


def test_pages_are_cached_per_domain(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    first = cached(tmp_path, client, "alfa.com.br")
    second = cached(tmp_path, client, "alfa.com.br")
    assert first == second and len(calls) == 1


def test_free_and_fake_domains_are_not_candidates():
    assert usable("alfasistemas.com.br")
    assert not usable("gmail.com")
    assert not usable("xxxxx.xxx.xx")
    assert not usable("not a domain")
