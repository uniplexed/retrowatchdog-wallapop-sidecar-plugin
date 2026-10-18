"""This deployment's settings, read once from the environment.

Nothing here is a secret or belongs to the app: a sidecar gets no database or
app credential. Pacing and retries are the app's.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

#: Every site this plugin knows (manifest.SITES), all served by default: a
#: declared source costs nothing until its market is switched on in the app.
DEFAULT_SITES = ("es", "it", "pt")

#: "Video games" and "PC games" (Wallapop's category tree, checked 2026-10-18).
#: Without them a title search also returns Funkos, books and decorations.
DEFAULT_SUBCATEGORY_IDS = ("10093", "24129")

DEFAULT_PORT = 8000

Location = Tuple[float, float]


@dataclass(frozen=True)
class Settings:
    #: Site keys (manifest.SITES); each one is the source `wallapop_<key>`.
    sites: Tuple[str, ...]
    port: int
    #: Wallapop subcategory ids every search is narrowed to.
    subcategory_ids: Tuple[str, ...]
    #: Per site key, the point searches are made from, overriding the site's
    #: default city. Wallapop ranks by distance from it.
    locations: Dict[str, Location]


class BadLocation(ValueError):
    """A WALLAPOP_LOCATION_<KEY> value that is not "latitude,longitude"."""


def load_settings(env: Optional[Mapping[str, str]] = None) -> Settings:
    values = os.environ if env is None else env
    locations: Dict[str, Location] = {}
    for name, value in values.items():
        if name.startswith("WALLAPOP_LOCATION_") and value.strip():
            locations[name[len("WALLAPOP_LOCATION_"):].lower()] = parse_location(name, value)
    return Settings(
        sites=tuple(s.lower() for s in _split(values.get("WALLAPOP_SITES", ""))) or DEFAULT_SITES,
        # a blank PORT means unset; int("") would raise before the server binds
        port=_optional_int(values.get("PORT", "")) or DEFAULT_PORT,
        subcategory_ids=_split(values.get("WALLAPOP_SUBCATEGORY_IDS", "")) or DEFAULT_SUBCATEGORY_IDS,
        locations=locations,
    )


def parse_location(name: str, value: str) -> Location:
    """ "40.4168,-3.7038" (as Google Maps copies it) to a (latitude, longitude) pair."""
    parts = [p.strip() for p in value.split(",")]
    try:
        lat, lon = (float(p) for p in parts)
    except ValueError:
        raise BadLocation(f'{name} must be "latitude,longitude", for example 40.4168,-3.7038; got {value!r}') from None
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise BadLocation(f"{name} is outside the globe: {value!r}")
    return (lat, lon)


def _split(value: str) -> Tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _optional_int(value: str) -> Optional[int]:
    value = value.strip()
    return int(value) if value else None
