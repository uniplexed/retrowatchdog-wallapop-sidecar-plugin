"""The HTTP surface, served on a loopback port; Wallapop is never called."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from app.config import Settings
from app.manifest import PROTOCOL_VERSION
from app.server import make_handler

SETTINGS = Settings(sites=("es", "it"), port=0, subcategory_ids=("10093",), locations={})

A_LISTING = {
    "sourceProductId": "nz08eqx81d6o",
    "title": "The Legend of Zelda: Ocarina of Time (N64)",
    "prices": [{"kind": "active_listing", "amount": 49.9, "currency": "EUR"}],
    "url": "https://es.wallapop.com/item/the-legend-of-zelda-ocarina-of-time-n64-1",
}


@pytest.fixture()
def serve():
    servers = []

    def start(search, settings=SETTINGS):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(settings, search))
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, json.loads(response.read())


def refused(url):
    with pytest.raises(urllib.error.HTTPError) as caught:
        get(url)
    return caught.value


def no_search(key, query, platform):  # pragma: no cover - must never be called
    raise AssertionError("the search path must not run for this request")


def test_health_answers_without_calling_wallapop(serve):
    status, body = get(f"{serve(no_search)}/health")
    assert status == 200
    assert body == {"status": "ok", "protocol": PROTOCOL_VERSION, "configured": True, "sources": ["wallapop_es", "wallapop_it"]}


def test_the_manifest_is_served_without_calling_wallapop(serve):
    status, body = get(f"{serve(no_search)}/manifest")
    assert status == 200
    assert [s["id"] for s in body["sources"]] == ["wallapop_es", "wallapop_it"]


def test_a_misconfigured_site_makes_the_manifest_a_500_naming_the_variable(serve):
    base = serve(no_search, Settings(sites=("xx",), port=0, subcategory_ids=(), locations={}))
    error = refused(f"{base}/manifest")
    assert error.code == 500
    assert "WALLAPOP_SITES" in json.loads(error.read())["error"]


def test_each_source_searches_its_own_site(serve):
    calls = []

    def search(key, query, platform):
        calls.append((key, query, platform))
        return [A_LISTING]

    base = serve(search)
    status, body = get(f"{base}/search?source=wallapop_it&q=ocarina%20of%20time&platform=n64&alt=Zeruda")
    assert (status, body) == (200, [A_LISTING])
    assert calls == [("it", "ocarina of time", "n64")]


def test_a_search_needs_a_source_and_a_query(serve):
    base = serve(no_search)
    assert refused(f"{base}/search?q=zelda").code == 400
    assert refused(f"{base}/search?source=wallapop_es").code == 400


def test_a_source_this_process_does_not_serve_is_a_404(serve):
    assert refused(f"{serve(no_search)}/search?source=wallapop_pt&q=zelda").code == 404


def test_a_failing_search_is_a_server_error_the_app_can_count(serve):
    def search(key, query, platform):
        raise RuntimeError("403 from Wallapop")

    assert refused(f"{serve(search)}/search?source=wallapop_es&q=zelda").code == 502


def test_an_unknown_path_is_a_404(serve):
    assert refused(f"{serve(no_search)}/items/1").code == 404
