"""MyUniStop: UCSB student housing marketplace (leases from property managers, subleases, rooms)."""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from bs4 import BeautifulSoup

from scrape import http
from scrape.model import Listing, Manager

log = logging.getLogger("myunistop")

BASE = "https://www.myunistop.com"
LIST_URL = BASE + "/allhousing-ucsb-offcampus/"
CATEGORIES = {"lease": "lease", "sublease": "sublease", "housemates_wanted": "room"}
MAX_AGE_DAYS = 60
MAX_PAGES = 15


def _age_days(text: str | None) -> int | None:
    """'57m ago' -> 0, '3d ago' -> 3, '2w ago' -> 14, '40w ago' -> 280."""
    if not text:
        return None
    m = re.search(r"(\d+)\s*(m|h|d|w|mo|y)\b", text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return {"m": 0, "h": 0, "d": n, "w": n * 7, "mo": n * 30, "y": n * 365}[unit]


def _money(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\$\s*([\d,]+)", text)
    return int(m.group(1).replace(",", "")) if m else None


def parse_list(html: str, kind: str) -> list[dict]:
    """Card summaries: detail path, title, age in days, category label, price."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    seen: set[str] = set()
    for card in soup.select(".listing.list-view"):
        body = card.select_one(".listing-details")
        if not body or not body.get("data-url"):
            continue
        path = body["data-url"]
        if path in seen:
            continue
        seen.add(path)
        title = body.select_one(".list-view-title")
        age = body.select_one(".created-time")
        typ = body.select_one(".comments.type")
        price = body.select_one(".lease-price")
        photos = [img["src"] for img in card.select(".media img[src]") if "my-media-cdn" in img["src"]]
        out.append(
            {
                "path": path,
                "title": title.get_text(strip=True) if title else None,
                "age_days": _age_days(age.get_text(strip=True) if age else None),
                "type": typ.get_text(strip=True) if typ else None,
                "price": _money(price.get_text() if price else None),
                "kind": kind,
                "photos": photos,
            }
        )
    return out


def parse_detail(html: str, path: str, kind: str, today: date | None = None) -> Listing | None:
    soup = BeautifulSoup(html, "lxml")
    info = soup.select_one(".information")
    if not info:
        return None
    lines = [ln.strip() for ln in info.get_text("\n").split("\n") if ln.strip()]
    address_line = lines[0] if lines else ""
    landlord = lines[1] if len(lines) > 1 and "$" not in lines[1] else None
    price_el = info.select_one(".extra-title")
    price_text = price_el.get_text(" ", strip=True) if price_el else None
    rent = _money(price_text)
    per_person = None
    if price_text:
        pp = re.search(r"\$\s*([\d,]+)\s*(?:-\s*\$?[\d,]+)?\s*/\s*person", price_text)
        if pp:
            per_person = int(pp.group(1).replace(",", ""))
        elif "/person" in price_text.replace(" ", "") and rent:
            per_person, rent = rent, None
    specs: dict[str, str] = {}
    for block in soup.select(".detail-spec"):
        parts = [p.strip() for p in block.get_text("\n", strip=True).split("\n") if p.strip()]
        if len(parts) >= 2:
            specs.setdefault(parts[0], " · ".join(parts[1:]))
    status = specs.get("Leasing Status", "")
    if "closed" in status.lower():
        return None
    m_id = re.search(r"/(\d+)/", path)
    source_id = m_id.group(1) if m_id else path
    street, _, city = address_line.partition(",")
    street = street.strip()
    city = city.strip() or None
    unit = None
    mu = re.search(r"\s+(#\s*[\w-]+|(?:apt|unit)\.?\s*[\w-]+)$", street, re.I)
    if mu:
        unit = re.sub(r"^(#|apt\.?|unit)\s*", "", mu.group(1), flags=re.I)
        street = street[: mu.start()].strip()
    desc_el = soup.select_one(".description .full-description, .description .short-description, .description")
    description = desc_el.get_text("\n", strip=True) if desc_el else None
    if description:
        description = re.sub(r"\n?See More$", "", description).strip()
    posted = soup.select_one(".specificDetails-posted-time")
    age = _age_days(posted.get_text(strip=True) if posted else None)
    posted_at = ((today or date.today()) - timedelta(days=age)).isoformat() if age is not None else None
    photos: list[str] = []
    for img in soup.select(".media img[src], .slider-media[src]"):
        src = img.get("src") or ""
        if "my-media-cdn" in src and src not in photos:
            photos.append(src)
    utilities = specs.get("Utilities")
    if utilities:
        mi = re.search(r"Included in rent:\s*·?\s*(.*?)(?:\s*·\s*Tenant pays:.*)?$", utilities)
        if mi:
            utilities = mi.group(1).strip(" ·") or utilities
    def beds_baths(k: str) -> float | None:
        v = specs.get(k)
        if not v:
            return None
        mm = re.search(r"\d+(?:\.\d+)?", v)
        return float(mm.group()) if mm else None
    title_el = soup.select_one("h1, .detail-title")
    return Listing(
        id=f"myunistop:{source_id}",
        source="myunistop",
        source_url=BASE + path,
        title=(title_el.get_text(strip=True) if title_el and title_el.get_text(strip=True) else address_line) or address_line,
        address=street or None,
        unit=unit,
        city=city,
        kind=kind,
        rent=rent,
        rent_per_person=per_person,
        rent_text=price_text,
        beds=beds_baths("Bedrooms"),
        baths=beds_baths("Bathrooms"),
        available=specs.get("Availability"),
        lease_term=specs.get("Lease Type & Max Residents") or specs.get("Lease Length"),
        furnished=specs.get("Furnishing"),
        utilities_included=utilities,
        pets=specs.get("Pet Policy"),
        parking=specs.get("Parking"),
        laundry=specs.get("Laundry"),
        amenities=[a for a in [specs.get("Room Type") and f"Room type: {specs['Room Type']}"] if a],
        description=description,
        photos=photos,
        manager=Manager(name=landlord),
        posted_at=posted_at,
    )


def fetch() -> list[Listing]:
    out: list[Listing] = []
    today = date.today()
    for category, kind in CATEGORIES.items():
        for page in range(1, MAX_PAGES + 1):
            html = http.get_text(LIST_URL, params={"page": page, "category": category})
            if not html:
                break
            cards = parse_list(html, kind)
            if not cards:
                break
            fresh = [c for c in cards if c["age_days"] is None or c["age_days"] <= MAX_AGE_DAYS]
            with ThreadPoolExecutor(max_workers=4) as ex:   # responses take several seconds; starts stay 1/s
                details = list(ex.map(lambda c: http.get_text(BASE + c["path"]), fresh))
            for c, detail in zip(fresh, details):
                if not detail:
                    continue
                lst = parse_detail(detail, c["path"], kind, today)
                if lst is None:
                    continue
                if c["title"] and lst.title == (lst.address or ""):
                    lst.title = c["title"]
                if not lst.photos:
                    lst.photos = c["photos"]
                if lst.rent is None and lst.rent_per_person is None and c["price"]:
                    lst.rent = c["price"]
                out.append(lst)
            if len(fresh) < len(cards):
                break   # listings are newest-first; the rest of this category is stale
            if not re.search(rf'href="\?page={page + 1}', html):
                break
        log.info("%s: %d listings so far", category, len(out))
    return out
