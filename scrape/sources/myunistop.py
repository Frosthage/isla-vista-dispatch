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
DETAIL_LIMIT = 80      # detail pages per run
WALL_LIMIT = 3         # consecutive login walls before giving up on details


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


def parse_list(html: str, kind: str, today: date | None = None) -> list[Listing]:
    """One Listing per card. Cards are public and carry title, street, beds/baths, type, price, photos and post age;
    the detail page (when reachable) fills in house number, landlord, description and lease specifics."""
    soup = BeautifulSoup(html, "lxml")
    out: list[Listing] = []
    seen: set[str] = set()
    for card in soup.select(".listing.list-view"):
        body = card.select_one(".listing-details")
        if not body or not body.get("data-url"):
            continue
        path = body["data-url"]
        if path in seen:
            continue
        seen.add(path)
        m_id = re.search(r"/(\d+)/", path)
        source_id = m_id.group(1) if m_id else path
        title_el = body.select_one(".list-view-title")
        title = title_el.get_text(strip=True) if title_el else path
        head = body.select_one("p.job_p_list strong")
        street = beds = baths = None
        if head:
            ht = head.get_text(" ", strip=True)
            street = ht.split("·")[0].strip() or None
            nums = re.findall(r"\d+(?:\.\d+)?", ht.split("·", 1)[1] if "·" in ht else "")
            if nums:
                beds = float(nums[0])
            if len(nums) > 1:
                baths = float(nums[1])
        age_el = body.select_one(".created-time")
        age = _age_days(age_el.get_text(strip=True) if age_el else None)
        typ_el = body.select_one(".comments.type")
        typ = typ_el.get_text(strip=True) if typ_el else None
        price_el = body.select_one(".lease-price")
        label_el = body.select_one(".rent-price-label")
        price = _money(price_el.get_text() if price_el else None)
        price_label = label_el.get_text(" ", strip=True) if label_el else ""
        rows: dict[str, str] = {}
        for p in body.select("p.job_p_list"):
            txt = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
            if ":" in txt and not p.select_one("strong"):
                k, _, v = txt.partition(":")
                rows[k.strip()] = v.strip()
        photos = [img["src"] for img in card.select(".media img[src]") if "my-media-cdn" in img["src"]]
        per_person = kind in ("sublease", "room") or "person" in price_label.lower()
        amenities = [f"{k}: {v}" for k, v in rows.items() if k in ("Room Type", "Preferred Gender", "Tenants Wanted")]
        out.append(
            Listing(
                id=f"myunistop:{source_id}",
                source="myunistop",
                source_url=BASE + path,
                title=title,
                address=street,
                city="Isla Vista" if street and re.search(r"del playa|sabado tarde|trigo|pasado|sueno|abrego|picasso|segovia|cordoba|pardall|madrid|seville|cervantes|el nido|el greco|camino|embarcadero|el colegio|estero|fortuna|sabado", street, re.I) else None,
                kind=kind,
                rent=None if per_person else price,
                rent_per_person=price if per_person else None,
                rent_text=(price_label + " " if price_label else "") + (f"${price:,}" if price else "") or None,
                beds=beds,
                baths=baths,
                available=rows.get("Availability") or rows.get("Dates"),
                lease_term=rows.get("Dates"),
                amenities=amenities,
                photos=photos,
                posted_at=((today or date.today()) - timedelta(days=age)).isoformat() if age is not None else None,
                geo_precision="approx",   # street only until the detail page adds the house number
            )
        )
    return out


def parse_detail(html: str, lst: Listing) -> str:
    """Fill lst from its detail page. Returns 'ok', 'wall' (login wall) or 'closed' (leasing closed)."""
    if "Sign in to continue" in html:
        return "wall"
    soup = BeautifulSoup(html, "lxml")
    info = soup.select_one(".information")
    if not info:
        return "wall"
    lines = [ln.strip() for ln in info.get_text("\n").split("\n") if ln.strip()]
    address_line = lines[0] if lines else ""
    landlord = lines[1] if len(lines) > 1 and "$" not in lines[1] else None
    price_el = info.select_one(".extra-title")
    price_text = price_el.get_text(" ", strip=True) if price_el else None
    specs: dict[str, str] = {}
    for block in soup.select(".detail-spec"):
        parts = [p.strip() for p in block.get_text("\n", strip=True).split("\n") if p.strip()]
        if len(parts) >= 2:
            specs.setdefault(parts[0], " · ".join(parts[1:]))
    if "closed" in specs.get("Leasing Status", "").lower():
        return "closed"
    street, _, city = address_line.partition(",")
    street = street.strip()
    unit = None
    mu = re.search(r"\s+(#\s*[\w-]+|(?:apt|unit)\.?\s*[\w-]+)$", street, re.I)
    if mu:
        unit = re.sub(r"^(#|apt\.?|unit)\s*", "", mu.group(1), flags=re.I)
        street = street[: mu.start()].strip()
    if street:
        lst.address = street
        lst.unit = unit
        lst.geo_precision = None if re.match(r"\d", street) else "approx"
    if city.strip():
        lst.city = city.strip()
    if price_text:
        lst.rent_text = price_text
        rent = _money(price_text)
        pp = re.search(r"\$\s*([\d,]+)\s*(?:-\s*\$?[\d,]+)?\s*/\s*person", price_text)
        if pp:
            lst.rent_per_person = int(pp.group(1).replace(",", ""))
            lst.rent = rent if "/mo" in price_text.replace(" ", "") and rent != lst.rent_per_person else None
        elif rent:
            if lst.kind == "lease":
                lst.rent, lst.rent_per_person = rent, None
            else:
                lst.rent_per_person = rent
    def num(k: str) -> float | None:
        v = specs.get(k)
        mm = re.search(r"\d+(?:\.\d+)?", v or "")
        return float(mm.group()) if mm else None
    lst.beds = num("Bedrooms") or lst.beds
    lst.baths = num("Bathrooms") or lst.baths
    lst.available = specs.get("Availability") or lst.available
    lst.lease_term = specs.get("Lease Type & Max Residents") or specs.get("Lease Length") or lst.lease_term
    lst.furnished = specs.get("Furnishing")
    utilities = specs.get("Utilities")
    if utilities:
        mi = re.search(r"Included in rent:\s*·?\s*(.*?)(?:\s*·\s*Tenant pays:.*)?$", utilities)
        utilities = (mi.group(1).strip(" ·") if mi else utilities) or None
    lst.utilities_included = utilities
    lst.pets = specs.get("Pet Policy")
    lst.parking = specs.get("Parking")
    lst.laundry = specs.get("Laundry")
    if specs.get("Room Type"):
        lst.amenities = [a for a in lst.amenities if not a.startswith("Room Type")] + [f"Room Type: {specs['Room Type']}"]
    desc_el = soup.select_one(".description .full-description, .description .short-description, .description")
    if desc_el:
        lst.description = re.sub(r"\n?See More$", "", desc_el.get_text("\n", strip=True)).strip() or None
    posted = soup.select_one(".specificDetails-posted-time")
    age = _age_days(posted.get_text(strip=True) if posted else None)
    if age is not None:
        lst.posted_at = (date.today() - timedelta(days=age)).isoformat()
    photos = [img["src"] for img in soup.select(".media img[src], .slider-media[src]") if "my-media-cdn" in (img.get("src") or "")]
    if photos:
        lst.photos = list(dict.fromkeys(photos))
    if landlord:
        lst.manager = Manager(name=landlord)
    return "ok"


def fetch() -> list[Listing]:
    today = date.today()
    cards: list[Listing] = []
    for category, kind in CATEGORIES.items():
        for page in range(1, MAX_PAGES + 1):
            html = http.get_text(LIST_URL, params={"page": page, "category": category})
            if not html:
                break
            got = parse_list(html, kind, today)
            if not got:
                break
            fresh = [l for l in got if l.posted_at is None or (today - date.fromisoformat(l.posted_at)).days <= MAX_AGE_DAYS]
            cards.extend(fresh)
            if len(fresh) < len(got) or not re.search(rf'href="\?page={page + 1}', html):
                break   # newest first; the rest of this category is stale
        log.info("%s: %d fresh cards", category, len(cards))
    # Detail pages sit behind a per-IP login wall after a few dozen views, so enrich newest-first,
    # one request at a time, and stop once the wall is up.
    cards.sort(key=lambda l: l.posted_at or "", reverse=True)
    out: list[Listing] = []
    walls = 0
    enriched = 0
    for lst in cards:
        status = None
        if walls < WALL_LIMIT and enriched < DETAIL_LIMIT:
            html = http.get_text(lst.source_url)
            if html:
                status = parse_detail(html, lst)
                if status == "wall":
                    walls += 1
                else:
                    walls = 0
                    enriched += 1
        if status == "closed":
            continue
        out.append(lst)
    log.info("%d listings, %d enriched from detail pages, stopped by login wall: %s", len(out), enriched, walls >= WALL_LIMIT)
    return out
