"""Craigslist Santa Barbara: apartments (apa), rooms (roo) and sublets (sub)."""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from scrape import http
from scrape.model import Listing

log = logging.getLogger("craigslist")

SEARCH_URL = "https://www.craigslist.org/search/area/santabarbara"
CATEGORIES = {"apa": "lease", "roo": "room", "sub": "sublease"}
QUERIES = ["isla vista", "goleta", "ucsb", "santa barbara"]


def parse_search(html: str) -> list[dict]:
    """The search page is JS-rendered but ships a no-JS result list."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for li in soup.select("li.cl-static-search-result"):
        a = li.select_one("a[href]")
        if not a:
            continue
        price = li.select_one(".price")
        loc = li.select_one(".location")
        out.append(
            {
                "url": a["href"],
                "title": li.get("title") or (li.select_one(".title").get_text(strip=True) if li.select_one(".title") else ""),
                "price": price.get_text(strip=True) if price else None,
                "location": loc.get_text(strip=True) if loc else None,
            }
        )
    return out


def parse_detail(html: str, url: str, kind: str, location: str | None = None) -> Listing | None:
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.select_one("#titletextonly")
    if not title_el:
        return None
    m_id = re.search(r"/(\d+)\.html|/([A-Za-z0-9_-]{10,})/?$", url)
    source_id = (m_id.group(1) or m_id.group(2)) if m_id else url
    price_el = soup.select_one(".price")
    rent = None
    if price_el:
        m = re.search(r"\$\s*([\d,]+)", price_el.get_text())
        rent = int(m.group(1).replace(",", "")) if m else None
    beds = baths = sqft = None
    housing = soup.select_one(".housing")
    if housing:
        h = housing.get_text(" ", strip=True)
        mb = re.search(r"(\d+)\s*br", h, re.I)
        ms = re.search(r"(\d+)\s*ft", h, re.I)
        beds = float(mb.group(1)) if mb else None
        sqft = int(ms.group(1)) if ms else None
    attrs: list[str] = []
    available = None
    for grp in soup.select(".attrgroup"):
        for span in grp.select("span.attr, span, div.attr"):
            t = span.get_text(" ", strip=True)
            if not t or t in attrs:
                continue
            mbb = re.match(r"(\d+)\s*BR\s*/\s*([\d.]+)\s*Ba", t, re.I)
            if mbb:
                beds = beds or float(mbb.group(1))
                baths = float(mbb.group(2))
                continue
            if re.match(r"\d+\s*ft", t):
                continue
            if t.lower().startswith("available"):
                available = re.sub(r"^available\s*", "", t, flags=re.I).strip() or "now"
                continue
            if ":" in t and t.endswith(":"):
                continue
            attrs.append(t)
    attrs = [a for a in attrs if not re.match(r"^(rent period|monthly)$", a, re.I)]
    laundry = next((a for a in attrs if "laundry" in a.lower() or "w/d" in a.lower()), None)
    parking = next((a for a in attrs if "parking" in a.lower() or "garage" in a.lower() or "carport" in a.lower()), None)
    pets = ", ".join(a for a in attrs if "cats" in a.lower() or "dogs" in a.lower()) or None
    furnished = next((a for a in attrs if "furnished" in a.lower()), None)
    map_el = soup.select_one("#map")
    lat = lng = None
    precision = None
    if map_el and map_el.get("data-latitude"):
        lat = float(map_el["data-latitude"])
        lng = float(map_el["data-longitude"])
        precision = "exact" if int(map_el.get("data-accuracy") or 0) <= 10 else "approx"
    addr_el = soup.select_one(".mapaddress")
    address = addr_el.get_text(" ", strip=True) if addr_el else None
    unit = None
    if address:
        mu = re.search(r"\s*(#\s*[\w-]+|(?:apt|unit)\.?\s*[\w-]+)$", address, re.I)
        if mu:
            unit = re.sub(r"^(#|apt\.?|unit)\s*", "", mu.group(1), flags=re.I)
            address = address[: mu.start()].strip()
    body = soup.select_one("#postingbody")
    description = None
    if body:
        for junk in body.select(".print-information, .print-qrcode-container, .print-qrcode-label"):
            junk.decompose()
        description = body.get_text("\n", strip=True)
        description = re.sub(r"^QR Code Link to This Post\s*", "", description)
    photos: list[str] = []
    m_imgs = re.search(r"var imgList = (\[.*?\]);", html, re.S)
    if m_imgs:
        for mu in re.finditer(r'"url":"([^"]+)"', m_imgs.group(1)):
            u = mu.group(1).replace("\\/", "/").replace("_600x450", "_1200x900")
            if u not in photos:
                photos.append(u)
    else:
        for img in soup.select(".gallery img, .swipe img, #thumbs img"):
            src = (img.get("src") or "").replace("_50x50c", "_1200x900").replace("_600x450", "_1200x900")
            if src and src not in photos:
                photos.append(src)
    time_el = soup.select_one("time.timeago[datetime], #display-date time[datetime]")
    posted_at = time_el["datetime"] if time_el else None
    city = None
    if location:
        city = location
    elif address:
        pass
    return Listing(
        id=f"craigslist:{source_id}",
        source="craigslist",
        source_url=url,
        title=title_el.get_text(strip=True),
        address=address,
        unit=unit,
        city=city,
        lat=lat,
        lng=lng,
        geo_precision=precision,
        kind=kind,
        rent=rent,
        rent_text=price_el.get_text(strip=True) if price_el else None,
        beds=beds,
        baths=baths,
        sqft=sqft,
        available=available,
        furnished=furnished,
        pets=pets,
        parking=parking,
        laundry=laundry,
        amenities=[a for a in attrs if a not in (laundry, parking, furnished) and a not in (pets or "")],
        description=description,
        photos=photos,
        posted_at=posted_at,
    )


def fetch() -> list[Listing]:
    seen: set[str] = set()
    out: list[Listing] = []
    for cat, kind in CATEGORIES.items():
        for q in QUERIES:
            html = http.get_text(SEARCH_URL, params={"cat": cat, "query": q})
            if not html:
                continue
            results = [r for r in parse_search(html) if r["url"] not in seen]
            seen.update(r["url"] for r in results)
            log.info("%s %r: %d new results", cat, q, len(results))
            with ThreadPoolExecutor(max_workers=4) as ex:
                details = list(ex.map(lambda r: http.get_text(r["url"]), results))
            for r, detail in zip(results, details):
                if not detail:
                    continue
                lst = parse_detail(detail, r["url"], kind, r.get("location"))
                if lst:
                    out.append(lst)
    return out
