"""One Wallapop search item to one raw protocol listing.

The sidecar fetches and never classifies: platform, region, completeness and
grade are read by the app's one shared classifier, since two sources
classifying separately would break cross-source comparison silently. Field
provenance is in ../README.md; read it before adding a field.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional

#: The protocol version, re-exported so there is only one constant.
from .manifest import PROTOCOL_VERSION  # noqa: F401  (imported for re-export)

#: Private sellers' asking prices: the only kind Wallapop can honestly send.
PRICE_KIND = "active_listing"

#: ISO 4217 alpha. An unknown code falls back to rate 1 app-side, and the
#: frozen USD amount would be wrong permanently.
_ISO_4217 = re.compile(r"^[A-Z]{3}$")

#: What a web slug may hold before it is put in a link.
_SLUG = re.compile(r"^[a-z0-9-]{1,300}$")


class ItemMappingError(ValueError):
    """This item cannot be expressed as a protocol listing, and why.

    Raised rather than repaired: a patched listing would sit beside real
    evidence with nothing saying it was a guess.
    """


def is_reserved(item: Dict[str, Any]) -> bool:
    """A reserved item is promised to a buyer: not a price anyone can pay."""
    reserved = item.get("reserved")
    return isinstance(reserved, dict) and reserved.get("flag") is True


def map_item(item: Dict[str, Any], host: str) -> Dict[str, Any]:
    """Map one search item to one raw listing, or refuse it.

    `host` (es.wallapop.com, …) only builds the link; it is never read as a region.
    """
    source_product_id = _text(item.get("id"))
    if source_product_id is None:
        raise ItemMappingError("item has no id, so the app could not key a mapping to it")

    title = _text(item.get("title"), strip=False)
    if title is None:
        raise ItemMappingError(f"item {source_product_id} has no title")

    return {
        "sourceProductId": source_product_id,
        # unedited: the app's matcher is tuned on real seller text
        "title": title,
        "prices": [_price(item.get("price"), source_product_id)],
        "url": _url(item.get("web_slug"), host),
    }


def _price(price: Any, source_product_id: str) -> Dict[str, Any]:
    """The asking price exactly as quoted: never converted, never fee-inclusive."""
    if not isinstance(price, dict):
        raise ItemMappingError(f"item {source_product_id} has no price")
    amount = price.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ItemMappingError(f"item {source_product_id} price {amount!r} is not a number")
    amount = float(amount)
    if not math.isfinite(amount) or amount < 0:
        raise ItemMappingError(f"item {source_product_id} price {amount!r} is not a finite, non-negative amount")

    currency = price.get("currency")
    if not isinstance(currency, str):
        raise ItemMappingError(f"item {source_product_id} has no currency")
    currency = currency.strip().upper()
    if not _ISO_4217.match(currency):
        raise ItemMappingError(f"item {source_product_id} currency {currency!r} is not an ISO 4217 code")

    return {"kind": PRICE_KIND, "amount": amount, "currency": currency}


def _url(slug: Any, host: str) -> Optional[str]:
    """The listing's page, or None when the slug is missing or odd.

    The app refuses the whole row for a bad link, and a listing is worth more
    than a link.
    """
    slug = _text(slug)
    if slug is None or not _SLUG.match(slug):
        return None
    return f"https://{host}/item/{slug}"


def _text(value: Any, strip: bool = True) -> Optional[str]:
    """A non-empty string, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip() if strip else value
