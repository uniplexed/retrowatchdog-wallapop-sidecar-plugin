"""What this sidecar declares itself to be: a PROPOSAL the app validates and a
person approves before any price is stored.

- ONE role, `buy_listing`: every Wallapop number is an asking price, so it
  must never become the `reference` baseline.
- `global` reach: a marketplace of private sellers, as the protocol defines
  it, even though Wallapop ranks by distance from one city.
- No `sellFeeRate`: only read for a `reference` reading, which this lacks.

One process serves every configured site, one source per site
(`wallapop_<key>`). The site decides country, currency, label, item host and
the default city searches start from; an unknown key is refused.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, NamedTuple

from .config import Location, Settings

PROTOCOL_VERSION = 3
PLUGIN_NAME = "wallapop"
PLUGIN_VERSION = "1.0.0"

#: Wallapop's terms of use: automated access needs Wallapop's express authorization.
TERMS_URL = "https://about.wallapop.com/condiciones-de-uso/"


class Site(NamedTuple):
    """The facts a Wallapop country fixes, and the app must be told."""

    #: Where a listing's page lives: https://<host>/item/<slug>.
    host: str
    #: ISO country code; must be one the app has a market in (COUNTRY_CODES).
    country: str
    #: What that site quotes; the app drops a listing in any other currency.
    currency: str
    #: The heading a user reads above these prices.
    label: str
    #: The capital: where a search starts unless WALLAPOP_LOCATION_<KEY> says otherwise.
    default_location: Location


#: Keyed by the WALLAPOP_SITES key; the source id is `wallapop_<key>`.
SITES: Mapping[str, Site] = {
    "es": Site(host="es.wallapop.com", country="ES", currency="EUR", label="Wallapop España", default_location=(40.4168, -3.7038)),
    "it": Site(host="it.wallapop.com", country="IT", currency="EUR", label="Wallapop Italia", default_location=(41.9028, 12.4964)),
    "pt": Site(host="pt.wallapop.com", country="PT", currency="EUR", label="Wallapop Portugal", default_location=(38.7223, -9.1393)),
}


class UnknownSite(Exception):
    """WALLAPOP_SITES names a site this manifest cannot describe.

    Raised, not defaulted: a guessed country would value copies in the wrong market.
    """


def source_id(key: str) -> str:
    return f"wallapop_{key}"


def served_sites(settings: Settings) -> Dict[str, Site]:
    """Source id -> site, for every configured key; an unknown key raises."""
    unknown = [key for key in settings.sites if key not in SITES]
    if unknown:
        raise UnknownSite(
            f"WALLAPOP_SITES names {', '.join(unknown)}, not a Wallapop site this sidecar can declare; "
            f"known sites: {', '.join(SITES)}"
        )
    return {source_id(key): SITES[key] for key in settings.sites}


def location_for(settings: Settings, key: str) -> Location:
    return settings.locations.get(key, SITES[key].default_location)


def manifest_payload(settings: Settings) -> Dict[str, Any]:
    return {
        "protocol": PROTOCOL_VERSION,
        "plugin": {"name": PLUGIN_NAME, "version": PLUGIN_VERSION},
        "requiredSecrets": [],
        "sources": [
            {
                "id": sid,
                "kind": "live",
                "label": site.label,
                "family": "wallapop",
                "familyLabel": "Wallapop",
                "country": site.country,
                "reach": "global",
                # listings rarely declare a region and the app must not invent
                # one from the site's country
                "defaultRegion": None,
                "expectedCurrencies": [site.currency],
                "kindRoles": {"active_listing": "buy_listing"},
                # "asking price", not "listing": the wording is the honesty
                "kindLabels": {"active_listing": f"{site.label} asking price"},
                "caveat": (
                    f"{site.label} is read through Wallapop's unofficial web API: asking prices from "
                    "private sellers near one city, best-effort. Wallapop's terms of use require its "
                    f"express authorization to use it: {TERMS_URL}"
                ),
            }
            for sid, site in served_sites(settings).items()
        ],
    }
