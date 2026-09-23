"""Local property managers that publish vacancies through AppFolio ({slug}.appfolio.com/listings).

AppFolio's robots.txt allows only the list page (Allow: /listings$) and disallows /listings/detail/,
so everything comes from the list page: rent, beds/baths, address, map coordinates, the first photo,
utilities, pet policy and a truncated description.
"""
from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from scrape import http
from scrape.model import Listing, Manager

log = logging.getLogger("appfolio")

# slug -> (company name, public website). Slugs verified 2026-09-23 by decoding the
# data-widget-config on each company's vacancies page.
COMPANIES: dict[str, tuple[str, str]] = {
    "playalifeiv": ("Playa Life IV", "https://www.playalifeiv.com"),
    "wolfeandassociates": ("Wolfe & Associates", "https://www.rlwa.com"),
    "ivproperties": ("IV Properties", "https://www.ivproperties.com"),
    "sfmvdm": ("SFM Vista Del Mar", "https://www.sfmvdm.com"),
    "excellencepm": ("Excellence in Property Management", "https://eipm.us.com"),
    "harwin": ("Harwin & Co.", "https://www.harwincosb.com"),
    "d63propmgmt": ("D63 Property Management", "https://www.d63propertymanagement.com"),
    "cochrane": ("Cochrane Property Management", "https://www.cochranepm.com"),
    "kotogroup": ("The Koto Group", "https://www.kotogroup.com"),
    "dmhproperties": ("DMH Properties", "https://www.dmhproperties.net"),
    "gallagherpm": ("Gallagher Property Management", "https://www.gpmproperties.com"),
}

PLACEHOLDER = "place_holder"


def _num(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else None


def _split_address(full: str) -> tuple[str | None, str | None, str | None, str | None]:
    """'6561 Del Playa, 5, Goleta, CA 93117' -> (street, unit, city, zip)."""
    parts = [p.strip() for p in full.split(",")]
    zip_code = None
    city = None
    if parts and re.search(r"\bCA\b", parts[-1]):
        m = re.search(r"(\d{5})", parts[-1])
        zip_code = m.group(1) if m else None
        parts = parts[:-1]
    if len(parts) >= 2:
        city = parts[-1]
        parts = parts[:-1]
    street = parts[0] if parts else full
    unit = None
    if len(parts) >= 2:
        unit = " ".join(parts[1:])
    else:
        m = re.search(r"\s+(#\s*[\w-]+|(?:apt|unit)\.?\s*[\w-]+)$", street, re.I)
        if m:
            unit = re.sub(r"^(#|apt\.?|unit)\s*", "", m.group(1), flags=re.I)
            street = street[: m.start()].strip()
    return street, unit, city, zip_code


def parse_list(html: str, slug: str) -> list[Listing]:
    soup = BeautifulSoup(html, "lxml")
    name, website = COMPANIES.get(slug, (slug, f"https://{slug}.appfolio.com"))
    markers: dict[str, dict] = {}
    m = re.search(r"markers:\s*(\[.*?\])\s*,?\s*\n", html, re.S)
    if m:
        try:
            for mk in json.loads(m.group(1)):
                markers[mk["detail_page_url"]] = mk
        except (ValueError, KeyError):
            log.warning("%s: could not parse map markers", slug)
    out: list[Listing] = []
    for item in soup.select(".listing-item.js-listing-item"):
        link = item.select_one("a.js-link-to-detail") or item.select_one("a[href*='/listings/detail/']")
        if not link:
            continue
        path = link["href"]
        uid = path.rsplit("/", 1)[-1]
        full_address = item.select_one(".js-listing-address").get_text(" ", strip=True)
        street, unit, city, zip_code = _split_address(full_address)
        rent_el = item.select_one(".js-listing-blurb-rent")
        bb_el = item.select_one(".js-listing-blurb-bed-bath")
        beds = baths = None
        if bb_el:
            bb = re.search(r"([\d.]+)\s*bd\s*/\s*([\d.]+)\s*ba", bb_el.get_text(" ", strip=True))
            if bb:
                beds, baths = float(bb.group(1)), float(bb.group(2))
        title_el = item.select_one(".js-listing-title")
        title = title_el.get_text(" ", strip=True) if title_el else full_address
        available = None
        av = re.search(r"available\s*(?:for)?:?\s*(.+)", title, re.I)
        if av:
            available = av.group(1).strip()
        desc_el = item.select_one(".js-listing-description")
        utilities = None
        pets = None
        for p in item.select("p"):
            t = p.get_text(" ", strip=True)
            mu = re.search(r"Utilities Included:\s*(.*?)(?:\s*(?:Pet Policy|Appliances|Amenities|Parking|Laundry|Lease Terms?):|$)", t)
            if mu and mu.group(1).strip(" ,"):
                utilities = mu.group(1).strip(" ,")
            mp = re.search(r"Pet Policy:\s*(.*)$", t)
            if mp:
                pets = mp.group(1).strip()
        img = item.select_one("img.js-listing-image")
        photos: list[str] = []
        if img:
            src = img.get("data-original") or img.get("src") or ""
            if src and PLACEHOLDER not in src:
                photos.append(src.replace("/medium.jpg", "/large.jpg"))
        marker = markers.get(path, {})
        lat = marker.get("latitude")
        lng = marker.get("longitude")
        rent = _num(rent_el.get_text() if rent_el else None)
        out.append(
            Listing(
                id=f"appfolio:{slug}:{uid}",
                source="appfolio",
                source_url=f"https://{slug}.appfolio.com{path}",
                title=title if not title.lower().startswith("available") else f"{street}{' #' + unit if unit else ''}",
                address=street,
                unit=unit,
                city=city,
                zip=zip_code,
                lat=float(lat) if lat is not None else None,
                lng=float(lng) if lng is not None else None,
                geo_precision="exact" if lat is not None else None,
                rent=int(rent) if rent else None,
                rent_text=rent_el.get_text(strip=True) if rent_el else None,
                beds=beds,
                baths=baths,
                available=available,
                utilities_included=utilities,
                pets=pets,
                description=desc_el.get_text("\n", strip=True) if desc_el else None,
                photos=photos,
                manager=Manager(name=name, website=website),
            )
        )
    return out


def fetch(slugs: list[str] | None = None) -> list[Listing]:
    out: list[Listing] = []
    for slug in slugs or COMPANIES:
        html = http.get_text(f"https://{slug}.appfolio.com/listings")
        if not html:
            log.warning("%s: no list page", slug)
            continue
        listings = parse_list(html, slug)
        log.info("%s: %d listings", slug, len(listings))
        out.extend(listings)
    return out
