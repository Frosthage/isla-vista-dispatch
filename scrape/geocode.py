"""Nominatim geocoding with a persistent cache, plus region classification."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from scrape import http

log = logging.getLogger("geocode")

CACHE_PATH = Path("data/geocode_cache.json")
_cache: dict[str, dict] | None = None

# Isla Vista: Storke Rd in the west to the UCSB campus edge in the east, ocean to Hollister.
IV_LAT = (34.404, 34.424)
IV_LNG = (-119.880, -119.842)
# South coast of Santa Barbara County: Gaviota to Carpinteria.
SOUTH_COAST_LAT = (34.36, 34.56)
SOUTH_COAST_LNG = (-120.25, -119.45)


def _load() -> dict[str, dict]:
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    return _cache


def merge_cache(extra: dict[str, dict]) -> None:
    """Merge a previously published cache (from the live site) into the local one."""
    c = _load()
    for k, v in extra.items():
        c.setdefault(k, v)


def save() -> None:
    if _cache is not None:
        CACHE_PATH.parent.mkdir(exist_ok=True)
        CACHE_PATH.write_text(json.dumps(_cache, indent=0, sort_keys=True))


def dump() -> dict[str, dict]:
    return dict(_load())


def normalize_address(address: str) -> str:
    a = address.strip()
    a = re.sub(r"\s+", " ", a)
    a = re.sub(r"\s*(#|apt\.?|apartment|unit|ste\.?|suite)\s*[\w-]+(?=\s*,|\s*$)", "", a, flags=re.I)
    # AppFolio style "6561 Del Playa, 5, Goleta": drop a short bare unit token between commas
    a = re.sub(r",\s*[A-Za-z]?\d{1,4}[A-Za-z]?\s*(?=,)", "", a)
    a = re.sub(r",\s*,", ",", a)
    return a.strip(" ,")


def geocode(address: str, city: str | None = None, zip_code: str | None = None) -> tuple[float, float] | None:
    """Return (lat, lng) or None. Address should be the street address without unit."""
    q = normalize_address(address)
    if city and city.lower() not in q.lower():
        q = f"{q}, {city}"
    if "CA" not in q and "California" not in q:
        q = f"{q}, CA"
    if zip_code and zip_code not in q:
        q = f"{q} {zip_code}"
    c = _load()
    if q in c:
        hit = c[q]
        return (hit["lat"], hit["lng"]) if hit else None
    r = http.get(
        "https://nominatim.openstreetmap.org/search",
        params={"format": "json", "limit": 1, "q": q, "countrycodes": "us"},
        headers={"User-Agent": http.UA},
    )
    result = None
    if r is not None:
        try:
            data = r.json()
        except ValueError:
            data = []
        if data:
            result = {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"]), "display": data[0].get("display_name")}
    c[q] = result
    if result is None:
        log.info("geocode miss: %s", q)
        return None
    return result["lat"], result["lng"]


def classify_region(lat: float | None, lng: float | None, city: str | None = None) -> str | None:
    """isla_vista | santa_barbara | None (outside the south coast)."""
    if city and city.strip().lower() == "isla vista":
        return "isla_vista"
    if lat is None or lng is None:
        return None
    if IV_LAT[0] <= lat <= IV_LAT[1] and IV_LNG[0] <= lng <= IV_LNG[1]:
        return "isla_vista"
    if SOUTH_COAST_LAT[0] <= lat <= SOUTH_COAST_LAT[1] and SOUTH_COAST_LNG[0] <= lng <= SOUTH_COAST_LNG[1]:
        return "santa_barbara"
    return None
