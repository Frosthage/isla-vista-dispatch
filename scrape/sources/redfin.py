"""Redfin rental search pages. Results are embedded in the page's React server state; detail pages are bot-checked."""
from __future__ import annotations

import json
import logging
import re

from scrape import http
from scrape.model import Listing

log = logging.getLogger("redfin")

BASE = "https://www.redfin.com"
PAGES = [
    BASE + "/city/23493/CA/Isla-Vista/rentals",
    BASE + "/city/7747/CA/Goleta/rentals",
    BASE + "/city/17669/CA/Santa-Barbara/rentals",
]
STATE_KEY = "root.__reactServerState.InitialContext = "
PHOTO = "https://ssl.cdn-redfin.com/photo/rent/{rid}/islphoto/genIsl.{pos}_{ver}.jpg"


def _homes(html: str) -> list[dict]:
    i = html.find(STATE_KEY)
    if i < 0:
        return []
    try:
        state, _ = json.JSONDecoder().raw_decode(html[i + len(STATE_KEY):])
    except ValueError:
        log.warning("could not decode server state")
        return []
    cache = (state.get("ReactServerAgent.cache") or {}).get("dataCache") or {}
    best: list[dict] = []
    for key, entry in cache.items():
        if "search/rentals" not in key or not isinstance(entry, dict):
            continue
        text = ((entry.get("res") or {}).get("text")) or ""
        if not text:
            continue
        text = text.removeprefix("{}&&")
        try:
            homes = json.loads(text).get("homes") or []
        except (ValueError, AttributeError):
            continue
        if len(homes) > len(best) or ("consolidateBuildings" in key and len(homes) == len(best)):
            best = homes
    return best


def parse_page(html: str) -> list[Listing]:
    out: list[Listing] = []
    for home in _homes(html):
        hd = home.get("homeData") or {}
        rx = home.get("rentalExtension") or {}
        addr = hd.get("addressInfo") or {}
        centroid = ((addr.get("centroid") or {}).get("centroid")) or {}
        rid = rx.get("rentalId")
        pid = hd.get("propertyId")
        if not rid or not hd.get("url"):
            continue
        price = rx.get("rentPriceRange") or {}
        beds = rx.get("bedRange") or {}
        baths = rx.get("bathRange") or {}
        sqft = rx.get("sqftRange") or {}
        photos: list[str] = []
        for rng in ((hd.get("photosInfo") or {}).get("photoRanges") or []):
            for pos in range(int(rng.get("startPos", 0)), int(rng.get("endPos", -1)) + 1):
                photos.append(PHOTO.format(rid=rid, pos=pos, ver=rng.get("version", "1")))
                if len(photos) >= 10:
                    break
            if len(photos) >= 10:
                break
        facts = [f.get("description") for f in (rx.get("keyFacts") or []) if f.get("description")]
        units_text = next((f for f in facts if re.search(r"units? available", f)), None)
        amenities = [f for f in facts if f != units_text]
        street = addr.get("formattedStreetLine")
        unit = None
        if street:
            mu = re.search(r"\s+(?:unit|apt|#)\s*([\w-]+)$", street, re.I)
            if mu:
                unit = mu.group(1)
                street = street[: mu.start()].strip()
        name = hd["url"].split("/")[3].replace("-", " ") if hd["url"].count("/") >= 4 and not re.match(r"^\d", hd["url"].split("/")[3]) else None
        rent_min = price.get("min")
        rent_max = price.get("max")
        rent_text = None
        if rent_min and rent_max and rent_max != rent_min:
            rent_text = f"${rent_min:,} – ${rent_max:,}"
        elif rent_min:
            rent_text = f"${rent_min:,}"
        out.append(
            Listing(
                id=f"redfin:{pid}",
                source="redfin",
                source_url=BASE + hd["url"],
                title=name or street or "Rental",
                address=street,
                unit=unit,
                city=addr.get("city"),
                zip=addr.get("zip"),
                lat=centroid.get("latitude"),
                lng=centroid.get("longitude"),
                geo_precision="exact" if centroid.get("latitude") is not None else None,
                kind="lease",
                rent=int(rent_min) if rent_min else None,
                rent_text=rent_text,
                beds=float(beds["min"]) if beds.get("min") is not None else None,
                baths=float(baths["min"]) if baths.get("min") is not None else None,
                sqft=int(sqft["min"]) if sqft.get("min") else None,
                available=units_text,
                amenities=amenities + (["Student housing"] if rx.get("isStudent") else []),
                description=rx.get("description"),
                photos=photos,
                posted_at=rx.get("freshnessTimestamp") or rx.get("lastUpdated"),
            )
        )
    return out


def fetch() -> list[Listing]:
    out: list[Listing] = []
    seen: set[str] = set()
    for url in PAGES:
        html = http.get_text(url)
        if not html:
            continue
        got = parse_page(html)
        log.info("%s: %d", url.rsplit("/", 2)[-2], len(got))
        for l in got:
            if l.id not in seen:
                seen.add(l.id)
                out.append(l)
    return out
