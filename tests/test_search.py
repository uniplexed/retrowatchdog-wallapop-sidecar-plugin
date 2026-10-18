"""The fetch: what is asked of Wallapop, and what survives the mapping.

The fixture is a real answer (2026-10-18, "ocarina of time" from Madrid), cut
to the fields the plugin reads: no seller id, description or location.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import Settings
from app.mapping import ItemMappingError, map_item
from app.search import HEADERS, search_listings, search_url

FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" / "search-ocarina-2026-10-18.json").read_text(encoding="utf-8"))
SETTINGS = Settings(sites=("es", "it", "pt"), port=0, subcategory_ids=("10093", "24129"), locations={})


def answering(body):
    calls = []

    def fetch(url):
        calls.append(url)
        return body

    return fetch, calls


def test_maps_every_item_of_a_real_answer():
    fetch, _ = answering(FIXTURE)
    listings = search_listings(SETTINGS, "es", "ocarina of time", fetch=fetch)

    assert len(listings) == 6
    first = listings[0]
    assert first == {
        "sourceProductId": "nz08eqx81d6o",
        "title": "The Legend of Zelda: Ocarina of Time (N64)",
        "prices": [{"kind": "active_listing", "amount": 49.9, "currency": "EUR"}],
        "url": f"https://es.wallapop.com/item/{FIXTURE['data']['section']['payload']['items'][0]['web_slug']}",
    }


def test_asks_from_the_site_city_narrowed_to_video_games():
    fetch, calls = answering(FIXTURE)
    search_listings(SETTINGS, "it", "zelda", platform="n64", fetch=fetch)

    url = urlparse(calls[0])
    params = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "api.wallapop.com"
    assert params == {
        "keywords": "zelda",
        "source": "search_box",
        "latitude": "41.9028",
        "longitude": "12.4964",
        "subcategory_ids": "10093,24129",
    }


def test_the_operators_city_moves_the_search():
    moved = Settings(sites=("es",), port=0, subcategory_ids=("10093",), locations={"es": (41.3874, 2.1686)})
    params = parse_qs(urlparse(search_url(moved, "es", "doom")).query)
    assert (params["latitude"], params["longitude"]) == (["41.3874"], ["2.1686"])


def test_says_who_is_asking_and_sends_the_header_wallapop_requires():
    assert "RetroWatchdog" in HEADERS["User-Agent"]
    assert HEADERS["X-DeviceOS"] == "0"


def test_links_point_at_the_site_that_was_searched():
    fetch, _ = answering(FIXTURE)
    listings = search_listings(SETTINGS, "pt", "ocarina", fetch=fetch)
    assert all(l["url"].startswith("https://pt.wallapop.com/item/") for l in listings)


def test_a_reserved_item_is_not_a_price_anyone_can_pay():
    items = [dict(FIXTURE["data"]["section"]["payload"]["items"][0], reserved={"flag": True})]
    fetch, _ = answering({"data": {"section": {"payload": {"items": items}}}})
    assert search_listings(SETTINGS, "es", "x", fetch=fetch) == []


def test_one_unmappable_item_costs_that_item_and_nothing_else():
    good = FIXTURE["data"]["section"]["payload"]["items"][0]
    bad = dict(good, id="x1", price={"amount": "free", "currency": "EUR"})
    fetch, _ = answering({"data": {"section": {"payload": {"items": [bad, good]}}}})
    assert [l["sourceProductId"] for l in search_listings(SETTINGS, "es", "x", fetch=fetch)] == ["nz08eqx81d6o"]


def test_an_empty_answer_is_an_answer():
    fetch, _ = answering({"data": {"section": {"payload": {"items": []}}}})
    assert search_listings(SETTINGS, "es", "nothing", fetch=fetch) == []


def test_a_changed_answer_shape_is_a_failure_not_an_empty_result():
    # "none found" would hide an outage from the app's breaker
    fetch, _ = answering({"error": "moved"})
    with pytest.raises(ValueError):
        search_listings(SETTINGS, "es", "x", fetch=fetch)


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"id": None}, "no id"),
        ({"title": "  "}, "no title"),
        ({"price": {"amount": -1, "currency": "EUR"}}, "non-negative"),
        ({"price": {"amount": 5, "currency": "euro"}}, "ISO 4217"),
    ],
)
def test_an_item_is_refused_rather_than_repaired(change, reason):
    item = dict(FIXTURE["data"]["section"]["payload"]["items"][0], **change)
    with pytest.raises(ItemMappingError) as caught:
        map_item(item, "es.wallapop.com")
    assert reason in str(caught.value)


def test_an_odd_slug_drops_the_link_and_keeps_the_listing():
    item = dict(FIXTURE["data"]["section"]["payload"]["items"][0], web_slug="../evil")
    assert map_item(item, "es.wallapop.com")["url"] is None
