"""Attach manager contact and lease-policy info from the IV Tenants Union rental guide and the Pardall Center roster."""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from scrape import http
from scrape.model import Listing

log = logging.getLogger("enrich")

IVTU_URL = "https://ivtu.as.ucsb.edu/iv-rental-data/"
PARDALL_URL = "https://pardallcenter.as.ucsb.edu/resources/leasing-companies/"

# Free-text manager names as they appear in sources -> canonical key used to match the IVTU/Pardall cards.
ALIASES = {
    "playa life iv": "playa life",
    "department 63": "d63 property management",
    "d63 property management": "d63 property management",
    "wolfe & associates": "wolfe and associates",
    "wolfe & associates property services": "wolfe and associates",
    "wolfe & associates property management": "wolfe and associates",
    "sfm vista del mar property management": "sfm vista del mar",
    "meridian group real estate management": "meridian group",
    "icon apartments": "icon apartments",
    "icon": "icon apartments",
    "sierra property management": "sierra property management",
    "excellence in property management": "excellence in property management, inc.",
    "bartlein & company, inc": "bartlein & company, inc.",
}


def _canon(name: str) -> str:
    n = re.sub(r"\s+", " ", name.strip().lower())
    n = n.replace("&amp;", "&")
    return ALIASES.get(n, n)


def parse_ivtu(html: str) -> dict[str, dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    cards: dict[str, dict[str, str]] = {}
    for card in soup.select(".rental-card"):
        title = card.select_one(".rental-title")
        if not title:
            continue
        info: dict[str, str] = {}
        text = card.get_text("\n", strip=True)
        m = re.search(r"~?\$[\d,]+(?:\s*[–-]\s*\$?[\d,]+)?\s*/person/mo", text)
        if m:
            info["Per-person price range"] = m.group(0)
        # "Label: value" rows
        for label in ("Guide Description", "Email", "Phone", "Property Locations", "Quiet Hours", "Floorplans",
                      "Ownership", "Applications", "Guarantor Required", "Gender Inclusive", "Sublets Allowed", "Utilities"):
            mm = re.search(rf"{re.escape(label)}:\s*\n?(.*?)(?=\n(?:Guide Description|Email|Phone|Website|Property Locations|Quiet Hours|Floorplans|Ownership|Applications|Guarantor Required|Gender Inclusive|Sublets Allowed|Utilities|Visit Website):|\Z)", text, re.S)
            if mm:
                v = re.sub(r"\s+", " ", mm.group(1)).strip()
                if v and v.lower() not in ("visit site",):
                    info[label] = v
        site = card.select_one("a[href^=http]")
        if site:
            info["Website"] = site["href"]
        tags = [t.get_text(strip=True) for t in card.select(".rental-card-header ~ * span, .tag, .badge")]
        for t in ("Pets Allowed", "Furnished", "Parking"):
            if t in text:
                info.setdefault("Tags", "")
                info["Tags"] = (info["Tags"] + ", " + t).strip(", ")
        cards[_canon(title.get_text(strip=True))] = info
    return cards


def parse_pardall(html: str) -> dict[str, dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, dict[str, str]] = {}
    text = soup.get_text("\n", strip=True)
    for line in text.split("\n"):
        pass
    # The page is a list of "Name | website | phone" rows, sometimes split over elements; use links + phone regex per row.
    for li in soup.select("li, p, tr"):
        t = li.get_text(" ", strip=True)
        if not t or len(t) > 200:
            continue
        phone = re.search(r"\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b", t)
        link = li.select_one("a[href^=http]")
        name = re.split(r"\s*[|•–-]\s*https?://|\s*\|\s*", t)[0].strip()
        if not name or name.lower().startswith("http"):
            continue
        if not (phone or link):
            continue
        entry: dict[str, str] = {}
        if phone:
            entry["Phone"] = phone.group(0)
        if link:
            entry["Website"] = link["href"]
        out[_canon(name)] = entry
    return out


def apply(listings: list[Listing]) -> None:
    ivtu_html = http.get_text(IVTU_URL)
    pardall_html = http.get_text(PARDALL_URL)
    ivtu = parse_ivtu(ivtu_html) if ivtu_html else {}
    pardall = parse_pardall(pardall_html) if pardall_html else {}
    log.info("IVTU cards: %d, Pardall roster: %d", len(ivtu), len(pardall))
    hits = 0
    for lst in listings:
        if not lst.manager.name:
            continue
        key = _canon(lst.manager.name)
        card = ivtu.get(key)
        roster = pardall.get(key)
        if card:
            hits += 1
            for k, v in card.items():
                if k in ("Email", "Phone", "Website"):
                    attr = k.lower()
                    if not getattr(lst.manager, attr):
                        setattr(lst.manager, attr, v)
                elif k not in ("Property Locations", "Floorplans"):
                    lst.policies.setdefault(k, v)
        if roster:
            if not lst.manager.phone and roster.get("Phone"):
                lst.manager.phone = roster["Phone"]
            if not lst.manager.website and roster.get("Website"):
                lst.manager.website = roster["Website"]
    log.info("enriched %d listings from IVTU", hits)
