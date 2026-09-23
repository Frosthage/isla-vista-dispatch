"""ApartmentGuide city pages embed their search results in Next.js page data."""
from __future__ import annotations

import json
import logging
import re

from scrape import http
from scrape.model import Listing, Manager

log = logging.getLogger("apartmentguide")

BASE = "https://www.apartmentguide.com"
PAGES = [
    BASE + "/apartments/California/Isla-Vista/",
    BASE + "/apartments/California/Goleta/",
    BASE + "/apartments/California/Santa-Barbara/",
]
PHOTO = "https://i.apartmentguide.com/t_3x2_fixed_webp_md/{id}"


def parse_page(html: str) -> list[Listing]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        items = data["props"]["pageProps"]["pageData"]["location"]["listingSearch"]["listings"]
    except (ValueError, KeyError, TypeError):
        log.warning("unexpected page data shape")
        return []
    out: list[Listing] = []
    for it in items:
        if it.get("offMarket"):
            continue
        loc = it.get("location") or {}
        address = it.get("address") or it.get("name")
        unit = None
        if address:
            mu = re.search(r"\s+(?:unit|apt|#)\s*([\w-]+)$", address, re.I)
            if mu:
                unit = mu.group(1)
                address = address[: mu.start()].strip()
        pr = it.get("priceRange") or {}
        rent = pr.get("min")
        beds = None
        br = it.get("bedRange") or {}
        if br.get("min") is not None:
            beds = float(br["min"])
        elif it.get("bedCountData"):
            beds = float(min(b["beds"] for b in it["bedCountData"]))
        baths = None
        bt = it.get("bathText") or ""
        mb = re.search(r"\d+(?:\.\d+)?", bt)
        if mb:
            baths = float(mb.group())
        sqft = None
        ms = re.search(r"([\d,]+)", it.get("squareFeetText") or "")
        if ms:
            sqft = int(ms.group(1).replace(",", ""))
        photos = [PHOTO.format(id=p["id"]) for p in (it.get("optimizedPhotos") or []) if p.get("id")]
        pmc = it.get("propertyManagementCompany")
        pmc_name = pmc.get("name") if isinstance(pmc, dict) else (pmc if isinstance(pmc, str) else None)
        per_unit = (it.get("propertyType") or "").upper() in ("CONDO", "HOUSE", "TOWNHOME", "APARTMENT_UNIT") or bool(unit)
        rent_text = it.get("priceText") or it.get("mapMarkerPriceText")
        beds_text = it.get("bedText")
        out.append(
            Listing(
                id=f"apartmentguide:{it.get('id')}",
                source="apartmentguide",
                source_url=BASE + it["urlPathname"] if it.get("urlPathname") else BASE,
                title=it.get("name") or address or "Listing",
                address=address,
                unit=unit,
                city=loc.get("city"),
                zip=loc.get("zip") or it.get("zipCode"),
                lat=loc.get("lat"),
                lng=loc.get("lng"),
                geo_precision="exact" if loc.get("lat") is not None else None,
                kind="lease",
                rent=int(rent) if rent else None,
                rent_text=(f"{rent_text} (from)" if rent_text and pr.get("max") and pr.get("max") != rent and not per_unit else rent_text),
                beds=beds,
                baths=baths,
                sqft=sqft,
                available=it.get("unitsAvailableText") or it.get("availabilityStatus"),
                lease_term=", ".join(it.get("leasingTerms") or []) or None,
                amenities=[a for a in (it.get("amenitiesHighlighted") or []) if isinstance(a, str)]
                + ([f"Bedrooms offered: {beds_text}"] if beds_text and "-" in beds_text else []),
                description=None,
                photos=photos,
                manager=Manager(name=pmc_name, phone=it.get("phoneDesktopText") or it.get("phoneMobileText"), website=it.get("website")),
                posted_at=(it.get("updatedAt") or None),
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
