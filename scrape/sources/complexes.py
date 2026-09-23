"""Purpose-built student communities with their own websites: Icon, Solis Isla Vista, State on Campus."""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from scrape import http
from scrape.model import Listing, Manager

log = logging.getLogger("complexes")


def fetch_icon() -> list[Listing]:
    """iconapts.com lists floor plans with per-bed 'From $X/mo' pricing."""
    base = "https://iconapts.com"
    html = http.get_text(base + "/floor-plans")
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out: list[Listing] = []
    seen: set[str] = set()
    for item in soup.select(".units-item"):
        title_el = item.select_one(".units-item__title")
        if not title_el:
            continue
        name = title_el.get_text(strip=True)
        if name in seen:
            continue
        seen.add(name)
        amounts = [a.get_text(strip=True) for a in item.select(".units-item__amount")]
        beds = 0.0 if amounts and amounts[0].upper().startswith("S") else (float(re.sub(r"[^\d.]", "", amounts[0])) if amounts and re.search(r"\d", amounts[0]) else None)
        baths = None
        if len(amounts) > 1:
            mb = re.search(r"\d+(?:\.\d+)?", amounts[1])
            baths = float(mb.group()) if mb else None
        price_el = item.select_one(".units-item__lg-text")
        price_text = price_el.get_text(strip=True) if price_el else None
        pp = None
        if price_text:
            m = re.search(r"\$\s*([\d,]+)", price_text)
            pp = int(m.group(1).replace(",", "")) if m else None
        img = item.select_one("img")
        photo = None
        if img and img.get("src"):
            src = img["src"]
            photo = src if src.startswith("http") else f"{base}/{src.lstrip('/')}"
        out.append(
            Listing(
                id=f"icon:{re.sub(r'[^a-z0-9]+', '-', name.lower())}",
                source="icon",
                source_url=base + "/availability",
                title=f"Icon · {name}",
                address="6545 Trigo Rd",
                city="Isla Vista",
                zip="93117",
                lat=34.41284,
                lng=-119.85584,
                geo_precision="exact",
                kind="lease",
                rent=None,
                rent_per_person=pp,
                rent_text=(price_text + " per bed") if price_text else None,
                beds=beds,
                baths=baths,
                lease_term="Individual (per-bed) leases, academic year",
                description="Purpose-built student community one block from UCSB, leased by the bed. Pricing shown is the lowest advertised per-bed rate for this floor plan.",
                photos=[photo] if photo else [],
                manager=Manager(name="Icon Apartments", phone="805-214-4797", website=base),
            )
        )
    return out


def fetch_solis() -> list[Listing]:
    """solisislavista.com publishes floor plans and photos; rents are quoted on request."""
    base = "https://solisislavista.com"
    html = http.get_text(base + "/pricing")
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    photos: list[str] = []
    for img in soup.select("img[src*='medialibrarycf.entrata.com'], img[data-src*='medialibrarycf.entrata.com'], img[src*='squarespace-cdn']"):
        src = img.get("data-src") or img.get("src")
        if src and src not in photos and not src.endswith(".svg"):
            photos.append(src)
    text = soup.get_text("\n", strip=True)
    plans = sorted(set(re.findall(r"(?i)\b(studio|[1-4] bed(?:room)?s?)\b", text)))
    return [
        Listing(
            id="solis:community",
            source="solis",
            source_url=base + "/pricing",
            title="Solis Isla Vista",
            address="6667 El Colegio Rd",
            city="Isla Vista",
            zip="93117",
            kind="lease",
            rent=None,
            rent_text="Pricing on request",
            lease_term="Academic-year leases",
            amenities=[f"Floor plans: {', '.join(plans)}"] if plans else [],
            description="Off-campus student housing on El Colegio Rd within walking distance of UCSB. Studio to 3-bedroom apartments; pricing and availability are published on the community's own site.",
            photos=photos[:10],
            manager=Manager(name="Solis Isla Vista", phone="805-456-3669", website=base),
        )
    ]


def fetch_state() -> list[Listing]:
    """statesantabarbara.com renders pricing client-side; capture floor plan names and photos."""
    base = "https://www.statesantabarbara.com"
    html = http.get_text(base + "/floor-plans/")
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    photos: list[str] = []
    for img in soup.select("img[src*='/wp-content/uploads/']"):
        src = img.get("src")
        if src and src not in photos and not src.endswith(".svg") and "logo" not in src.lower():
            photos.append(src)
    return [
        Listing(
            id="state:community",
            source="state",
            source_url=base + "/floor-plans/",
            title="State on Campus Santa Barbara",
            address="6655 Sabado Tarde Rd",
            city="Isla Vista",
            zip="93117",
            kind="lease",
            rent=None,
            rent_text="Pricing on request",
            lease_term="Individual (per-bed) leases, academic year",
            description="Purpose-built student apartments in Isla Vista leased by the bed. Floor plan pricing is loaded interactively on the community's site.",
            photos=photos[:10],
            manager=Manager(name="State on Campus", phone="805-465-7379", website=base),
        )
    ]


def fetch() -> list[Listing]:
    out: list[Listing] = []
    for fn in (fetch_icon, fetch_solis, fetch_state):
        try:
            got = fn()
        except Exception:
            log.exception("%s failed", fn.__name__)
            got = []
        log.info("%s: %d", fn.__name__, len(got))
        out.extend(got)
    return out
