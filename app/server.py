"""The HTTP surface: GET /health, GET /manifest and GET /search, and nothing else.

Standard library only, so the image has no dependency to pin.
ThreadingHTTPServer so a slow search cannot block the healthcheck. No pacing,
retry, cache or timeout policy here: those belong to the app.
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from .config import Settings, load_settings
from .manifest import PROTOCOL_VERSION, SITES, UnknownSite, manifest_payload, source_id
from .search import search_listings

log = logging.getLogger(__name__)

#: (site key, query, platform hint) -> raw listings. Injected so the surface can
#: be exercised without calling Wallapop.
SearchFn = Callable[[str, str, Optional[str]], List[Dict[str, Any]]]


def health_payload(settings: Settings) -> Dict[str, Any]:
    """What /health says. `status` is about this process, not Wallapop; the
    app's circuit breaker reacts to real search failures. `configured` is
    always True: a public site needs no credential.
    """
    return {
        "status": "ok",
        "protocol": PROTOCOL_VERSION,
        "configured": True,
        "sources": [source_id(key) for key in settings.sites],
    }


def make_handler(settings: Settings, search: SearchFn):
    # source id -> site key; an unknown key serves nothing and fails /manifest
    served = {source_id(key): key for key in settings.sites if key in SITES}

    class SidecarHandler(BaseHTTPRequestHandler):
        server_version = f"retrowatchdog-sidecar/{PROTOCOL_VERSION}"
        # a connection that never sends its request line releases its thread
        timeout = 30

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
            route = urlparse(self.path)
            if route.path == "/health":
                self._json(200, health_payload(settings))
            elif route.path == "/manifest":
                self._manifest()
            elif route.path == "/search":
                self._search(parse_qs(route.query))
            else:
                self._json(404, {"error": f"no such endpoint: {route.path}"})

        def _manifest(self) -> None:
            try:
                self._json(200, manifest_payload(settings))
            except UnknownSite as error:
                # 500: the deployment is misconfigured; the app shows this as the plugin's last error
                log.error("cannot build a manifest: %s", error)
                self._json(500, {"error": str(error)})

        def _search(self, params: Dict[str, List[str]]) -> None:
            # Unknown parameters (e.g. `alt`) are ignored so the app can grow.
            source = _first(params.get("source"))
            if source is None:
                self._json(400, {"error": "source is required"})
                return
            key = served.get(source)
            if key is None:
                self._json(404, {"error": f"this sidecar does not serve {source!r}"})
                return
            query = _first(params.get("q"))
            if query is None:
                self._json(400, {"error": "q is required"})
                return
            try:
                listings = search(key, query, _first(params.get("platform")))
            except Exception as error:  # noqa: BLE001 - every failure is the app's to count
                log.exception("search failed")
                # a failure must be a status, never an empty 200: the app's breaker counts statuses
                self._json(502, {"error": f"{type(error).__name__}: {error}"})
                return
            self._json(200, listings)

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:
            log.info("%s %s", self.address_string(), fmt % args)

    return SidecarHandler


def _first(values: Optional[List[str]]) -> Optional[str]:
    if not values:
        return None
    value = values[0].strip()
    return value or None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    handler = make_handler(settings, lambda key, query, platform: search_listings(settings, key, query, platform))
    # every interface inside the container; compose publishes no host port for it
    server = ThreadingHTTPServer(("", settings.port), handler)
    log.info(
        "wallapop sidecar serving %s on port %s (protocol %s)",
        ", ".join(source_id(key) for key in settings.sites),
        settings.port,
        PROTOCOL_VERSION,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
