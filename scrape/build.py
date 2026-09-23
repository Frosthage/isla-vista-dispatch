"""Dedupe, diff against the previous run, and render the static site."""
from __future__ import annotations

import json
import logging
import re
import shutil
from collections import Counter
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scrape.model import Listing

log = logging.getLogger("build")

HERE = Path(__file__).parent
REGIONS = {
    "isla_vista": {"slug": "isla-vista", "name": "Isla Vista", "center": [34.4133, -119.8610], "zoom": 15},
    "santa_barbara": {"slug": "santa-barbara", "name": "Santa Barbara", "center": [34.4300, -119.7600], "zoom": 12},
}
SOURCE_NAMES = {
    "appfolio": "Property manager (AppFolio)",
    "meridian": "Meridian Group",
    "sierra": "Sierra Property Management",
    "myunistop": "MyUniStop",
    "craigslist": "Craigslist",
    "redfin": "Redfin",
    "apartmentguide": "ApartmentGuide",
    "icon": "Icon Apartments",
    "solis": "Solis Isla Vista",
    "state": "State on Campus",
    "ivtu": "IV Tenants Union",
}


def slug_id(listing_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", listing_id).strip("-").lower()


def _dedupe_key(lst: Listing) -> str | None:
    if not lst.address:
        return None
    a = lst.address.lower()
    a = re.sub(r"\b(drive|dr|road|rd|street|st|avenue|ave|lane|ln|way|court|ct|place|pl)\b\.?", "", a)
    a = re.sub(r"[^a-z0-9 ]", " ", a)
    a = re.sub(r"\s+", " ", a).strip()
    m = re.match(r"(\d+)\s+(\w+)", a)
    if not m:
        return None
    unit = re.sub(r"[^a-z0-9]", "", (lst.unit or "").lower())
    beds = "" if lst.beds is None else str(lst.beds)
    return f"{m.group(1)}|{m.group(2)}|{unit}|{beds}"


def _richness(lst: Listing) -> int:
    score = 0
    for f in ("rent", "beds", "baths", "sqft", "available", "description", "lat", "utilities_included", "pets", "lease_term"):
        if getattr(lst, f):
            score += 1
    score += min(len(lst.photos), 5)
    if lst.source in ("appfolio", "meridian"):
        score += 3   # the property manager is the primary source
    return score


def dedupe(listings: list[Listing]) -> list[Listing]:
    groups: dict[str, list[Listing]] = {}
    singles: list[Listing] = []
    for lst in listings:
        k = _dedupe_key(lst)
        if k is None:
            singles.append(lst)
        else:
            groups.setdefault(k, []).append(lst)
    out = list(singles)
    for members in groups.values():
        members.sort(key=_richness, reverse=True)
        primary = members[0]
        for other in members[1:]:
            primary.also_on.append({"source": other.source, "url": other.source_url})
            if not primary.photos and other.photos:
                primary.photos = list(other.photos)
            if not primary.description and other.description:
                primary.description = other.description
            if primary.lat is None and other.lat is not None:
                primary.lat, primary.lng, primary.geo_precision = other.lat, other.lng, other.geo_precision
            if primary.rent is None and other.rent is not None:
                primary.rent, primary.rent_text = other.rent, other.rent_text
        out.append(primary)
    return out


def apply_history(listings: list[Listing], previous: list[dict], today: str) -> None:
    prev = {p["id"]: p for p in previous}
    for lst in listings:
        p = prev.get(lst.id)
        lst.last_seen = today
        if p is None:
            lst.first_seen = today
            lst.price_history = [{"date": today, "rent": lst.rent}] if lst.rent else []
            continue
        lst.first_seen = p.get("first_seen") or today
        hist = list(p.get("price_history") or [])
        last_rent = hist[-1]["rent"] if hist else None
        if lst.rent is not None and lst.rent != last_rent:
            hist.append({"date": today, "rent": lst.rent})
        lst.price_history = hist


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["money"] = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else (v or "")
    env.filters["num"] = lambda v: ("" if v is None else (str(int(v)) if float(v).is_integer() else str(v)))
    env.globals["source_name"] = lambda s: SOURCE_NAMES.get(s, s)
    env.globals["slug_id"] = slug_id
    return env


def render(listings: list[Listing], out_dir: Path, today: str, geocode_cache: dict) -> None:
    env = _env()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "static").mkdir(exist_ok=True)
    for f in (HERE / "static").iterdir():
        shutil.copy(f, out_dir / "static" / f.name)

    def sort_key(l: Listing):
        return (0 if l.first_seen == today else 1, l.rent or 10**9)

    by_region: dict[str, list[Listing]] = {r: [] for r in REGIONS}
    for lst in listings:
        if lst.region in by_region:
            by_region[lst.region].append(lst)
    for r in by_region:
        by_region[r].sort(key=sort_key)

    counts = {r: len(v) for r, v in by_region.items()}
    new_counts = {r: sum(1 for l in v if l.first_seen == today) for r, v in by_region.items()}
    (out_dir / "index.html").write_text(
        env.get_template("index.html").render(regions=REGIONS, counts=counts, new_counts=new_counts, today=today, root="")
    )
    for r, meta in REGIONS.items():
        items = by_region[r]
        d = out_dir / meta["slug"]
        d.mkdir(exist_ok=True)
        sources = Counter(l.source for l in items)
        cities = Counter(l.city for l in items if l.city)
        data = [
            {
                "id": slug_id(l.id), "lat": l.lat, "lng": l.lng, "rent": l.rent, "beds": l.beds, "kind": l.kind,
                "title": l.title, "address": l.address, "unit": l.unit, "photo": (l.photos[0] if l.photos else None),
                "new": l.first_seen == today, "source": l.source,
            }
            for l in items
        ]
        (d / "index.html").write_text(
            env.get_template("region.html").render(
                region=meta, region_key=r, listings=items, data_json=json.dumps(data), today=today, root="../",
                sources=sources.most_common(), cities=cities.most_common(), new_count=new_counts[r],
            )
        )
    ld = out_dir / "l"
    ld.mkdir(exist_ok=True)
    for lst in listings:
        if lst.region not in REGIONS:
            continue
        (ld / f"{slug_id(lst.id)}.html").write_text(
            env.get_template("listing.html").render(l=lst, region=REGIONS[lst.region], today=today, root="../")
        )
    (out_dir / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (out_dir / "listings.json").write_text(json.dumps([l.to_dict() for l in listings], indent=0))
    (out_dir / "geocode_cache.json").write_text(json.dumps(geocode_cache, indent=0, sort_keys=True))
    log.info("rendered %d listings (%s)", len(listings), ", ".join(f"{REGIONS[r]['name']}: {c}" for r, c in counts.items()))
