"""What this plugin declares about itself, and why each field is that value."""

import pytest

from app.config import Settings, load_settings
from app.manifest import PROTOCOL_VERSION, SITES, UnknownSite, location_for, manifest_payload


def settings_for(*sites: str, **locations) -> Settings:
    return Settings(sites=sites or ("es",), port=0, subcategory_ids=(), locations=locations)


def a_source(site: str = "es") -> dict:
    return manifest_payload(settings_for(site))["sources"][0]


def test_manifest_declares_protocol_3_and_one_source_per_site():
    manifest = manifest_payload(load_settings({}))
    assert manifest["protocol"] == PROTOCOL_VERSION == 3
    assert manifest["plugin"]["name"] == "wallapop"
    assert manifest["requiredSecrets"] == []
    assert [s["id"] for s in manifest["sources"]] == ["wallapop_es", "wallapop_it", "wallapop_pt"]


def test_only_the_configured_sites_are_declared():
    assert [s["id"] for s in manifest_payload(settings_for("pt", "es"))["sources"]] == ["wallapop_pt", "wallapop_es"]


def test_wallapop_quotes_asking_prices_and_nothing_else():
    # what a private seller ASKS is not what anything sold for: one role only,
    # never `reference`
    source = a_source()
    assert source["kindRoles"] == {"active_listing": "buy_listing"}
    assert source["kindLabels"] == {"active_listing": "Wallapop España asking price"}
    assert source["reach"] == "global"
    assert source["defaultRegion"] is None
    assert source["kind"] == "live"


def test_each_site_declares_its_own_country_and_heading():
    italian = a_source("it")
    assert italian["country"] == "IT"
    assert italian["expectedCurrencies"] == ["EUR"]
    assert italian["label"] == "Wallapop Italia"
    assert "unofficial" in italian["caveat"].lower()
    # the terms are where a user reads the source's prices, not only in a README
    assert "express authorization" in italian["caveat"]
    assert "https://about.wallapop.com/condiciones-de-uso/" in italian["caveat"]


def test_an_unknown_site_is_refused_rather_than_guessed():
    with pytest.raises(UnknownSite) as caught:
        manifest_payload(settings_for("es", "fr"))
    assert "WALLAPOP_SITES" in str(caught.value)
    assert "es, it, pt" in str(caught.value)


def test_every_site_names_a_country_the_app_has_a_market_in():
    # COUNTRY_CODES in the app repository, packages/shared/src/index.ts
    app_countries = {"GB", "ES", "IE", "DE", "FR", "IT", "PT", "US"}
    assert {site.country for site in SITES.values()} <= app_countries
    assert len({site.country for site in SITES.values()}) == len(SITES)


def test_a_search_starts_from_the_capital_unless_the_operator_moved_it():
    assert location_for(settings_for("es"), "es") == (40.4168, -3.7038)
    assert location_for(settings_for("es", es=(41.3874, 2.1686)), "es") == (41.3874, 2.1686)
    assert location_for(settings_for("it"), "it") == (41.9028, 12.4964)
    assert location_for(settings_for("pt"), "pt") == (38.7223, -9.1393)
