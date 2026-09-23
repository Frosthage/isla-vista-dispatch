from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Manager:
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None


@dataclass
class Listing:
    id: str                      # "{source}:{source_id}"
    source: str                  # appfolio, meridian, myunistop, craigslist, redfin, apartmentguide, icon, solis, state
    source_url: str
    title: str
    address: str | None = None   # street address without unit
    unit: str | None = None
    city: str | None = None
    zip: str | None = None
    lat: float | None = None
    lng: float | None = None
    geo_precision: str | None = None   # exact | geocoded | approx
    region: str | None = None          # isla_vista | santa_barbara
    kind: str = "lease"                # lease | sublease | room
    rent: int | None = None            # whole-unit monthly rent in USD
    rent_per_person: int | None = None
    rent_text: str | None = None
    beds: float | None = None
    baths: float | None = None
    sqft: int | None = None
    available: str | None = None       # ISO date or free text ("2027-28 School Year")
    lease_term: str | None = None
    furnished: str | None = None
    utilities_included: str | None = None
    pets: str | None = None
    parking: str | None = None
    laundry: str | None = None
    amenities: list[str] = field(default_factory=list)
    description: str | None = None
    photos: list[str] = field(default_factory=list)   # source URLs before download, local paths after
    manager: Manager = field(default_factory=Manager)
    policies: dict[str, str] = field(default_factory=dict)
    posted_at: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None
    price_history: list[dict[str, Any]] = field(default_factory=list)
    also_on: list[dict[str, str]] = field(default_factory=list)   # [{"source":..., "url":...}]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Listing":
        d = dict(d)
        d["manager"] = Manager(**(d.get("manager") or {}))
        return Listing(**d)
