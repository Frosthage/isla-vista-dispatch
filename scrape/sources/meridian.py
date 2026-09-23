"""Meridian Group Real Estate Management (Rent Manager website): one listing per available unit."""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from scrape import http
from scrape.model import Listing, Manager

log = logging.getLogger("meridian")

BASE = "https://meridiangrouprem.com"
LIST_URLS = [BASE + "/properties/?ptype=islavista", BASE + "/properties/?ptype=residential"]
MANAGER = Manager(name="Meridian Group", phone="(805) 692-2500", website="https://meridiangrouprem.com")


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for w in soup.select(".rmwb_listing-wrapper"):
        link = next((a["href"] for a in w.select("a[href]") if a["href"].startswith("http") and "/properties/" in a["href"]), None)
        if not link:
            continue
        out.append(
            {
                "url": link,
                "propid": w.get("data-propid"),
                "street": w.get("data-street") or w.get("data-propname"),
                "city": w.get("data-city"),
                "zip": w.get("data-zip"),
                "type": w.get("data-proptype") or w.get("data-category"),
                "image": (w.get("data-image") or "").replace("&amp;", "&") or None,
                "starting_rent": w.get("data-rent"),
            }
        )
    return out


def parse_detail(html: str, prop: dict) -> list[Listing]:
    soup = BeautifulSoup(html, "lxml")
    photos: list[str] = []
    for img in soup.select(".slider-for img, .slider-nav img"):
        src = (img.get("data-lazy") or img.get("src") or "").replace("&amp;", "&")
        if src and "rentmanager" in src and src not in photos:
            photos.append(src)
    if not photos and prop.get("image"):
        photos.append(prop["image"])
    amenities = [li.get_text(" ", strip=True) for li in soup.select(".amenity-list li")]
    desc = None
    for p in soup.select("p"):
        t = p.get_text(" ", strip=True)
        if len(t) > 120 and "$" not in t[:5]:
            desc = t
            break
    out: list[Listing] = []
    for u in soup.select(".rmwb-unit-wrapper"):
        unit_name = u.select_one(".info-item")
        unit = re.sub(r"^unit\s*", "", unit_name.get_text(strip=True), flags=re.I) if unit_name else None
        def num(attr: str) -> float | None:
            v = u.get(attr)
            try:
                return float(v) if v not in (None, "", "N/A") else None
            except ValueError:
                return None
        rent = num("data-rent")
        sqft = num("data-squarefootage")
        link = u.select_one("a[href*='/units/']")
        uid = f"{prop['propid']}-{re.sub(r'[^A-Za-z0-9]', '', unit or '')}"
        out.append(
            Listing(
                id=f"meridian:{uid}",
                source="meridian",
                source_url=(link["href"] if link else prop["url"]),
                title=f"{prop['street']}{' #' + unit if unit else ''}",
                address=prop["street"],
                unit=unit,
                city=prop.get("city"),
                zip=prop.get("zip"),
                rent=int(rent) if rent else None,
                beds=num("data-beds"),
                baths=num("data-baths"),
                sqft=int(sqft) if sqft and sqft > 0 else None,
                available=u.get("data-availabledate") or None,
                amenities=amenities,
                description=desc,
                photos=photos,
                manager=Manager(**MANAGER.__dict__),
            )
        )
    return out


def fetch() -> list[Listing]:
    out: list[Listing] = []
    seen: set[str] = set()
    for url in LIST_URLS:
        html = http.get_text(url)
        if not html:
            continue
        for prop in parse_list(html):
            if prop["url"] in seen:
                continue
            seen.add(prop["url"])
            detail = http.get_text(prop["url"])
            if detail:
                out.extend(parse_detail(detail, prop))
    return out
