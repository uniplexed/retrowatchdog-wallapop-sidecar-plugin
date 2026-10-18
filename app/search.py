"""The fetch: ask Wallapop's web API, map what comes back, drop what will not map.

One GET per search, from the site's city, narrowed to the video game
subcategories. The platform hint is accepted and NOT used: Wallapop has no
per-console category, and the app's matcher reads the platform from titles.
No pacing, retry or cache here: those belong to the app.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

from .config import Settings
from .manifest import SITES, location_for
from .mapping import ItemMappingError, is_reserved, map_item

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.wallapop.com/api/v3/search"

#: Wallapop answers 403 without X-DeviceOS; with it, it accepts a user agent
#: that says who is asking (checked 2026-10-18), so this one does.
HEADERS = {
    "User-Agent": "RetroWatchdog-wallapop-plugin (+https://github.com/uniplexed/retrowatchdog-wallapop-sidecar-plugin)",
    "Accept": "application/json",
    "X-DeviceOS": "0",
}

#: A hung socket must not hold a request thread forever; the app's own budget
#: is shorter and decides what the user waits for.
TIMEOUT_SECONDS = 30

#: url -> parsed JSON body. Injected in tests; the default makes the real call.
Fetch = Callable[[str], Any]


#: One answer is about 40 items, well under a megabyte; this bounds what a
#: hostile or broken upstream can make the process hold.
MAX_RESPONSE_BYTES = 8_000_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would make this process fetch and parse whatever host it names."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - stdlib hook
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def http_get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers=HEADERS)
    with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError(f"Wallapop answered more than {MAX_RESPONSE_BYTES} bytes")
        return json.loads(data.decode("utf-8"))


def search_url(settings: Settings, key: str, query: str) -> str:
    lat, lon = location_for(settings, key)
    params = {
        "keywords": query,
        "source": "search_box",
        "latitude": lat,
        "longitude": lon,
        "subcategory_ids": ",".join(settings.subcategory_ids),
    }
    return f"{SEARCH_URL}?{urlencode(params)}"


def search_listings(
    settings: Settings,
    key: str,
    query: str,
    platform: Optional[str] = None,
    fetch: Fetch = http_get_json,
) -> List[Dict[str, Any]]:
    if platform:
        log.debug("platform hint %s ignored: Wallapop has no per-console category", platform)

    body = fetch(search_url(settings, key, query))
    try:
        items = body["data"]["section"]["payload"]["items"]
    except (KeyError, TypeError):
        # a changed answer shape is a failure the app must count, not "none found"
        raise ValueError("Wallapop answered without data.section.payload.items") from None
    if not isinstance(items, list):
        raise ValueError("Wallapop's items is not a list")

    host = SITES[key].host
    listings: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or is_reserved(item):
            continue
        try:
            listings.append(map_item(item, host))
        except ItemMappingError as error:
            # one bad item costs only itself; logged so the maintainer sees it
            log.warning("dropping an item: %s", error)
    return listings
