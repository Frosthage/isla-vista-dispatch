from datetime import date
from pathlib import Path

from scrape.model import Listing
from scrape.sources.myunistop import parse_list, parse_detail, _age_days

FIX = Path(__file__).parent / "fixtures"


def test_age_parsing():
    assert _age_days("57m ago") == 0
    assert _age_days("3d ago") == 3
    assert _age_days("2w ago") == 14
    assert _age_days("40w ago") == 280
    assert _age_days(None) is None


def test_list_cards_become_listings():
    listings = parse_list((FIX / "myunistop_list.html").read_text(), "sublease", date(2026, 9, 23))
    assert len(listings) >= 20
    first = listings[0]
    assert first.id == "myunistop:2691"
    assert first.source_url.startswith("https://www.myunistop.com/subleasedetail/2691/")
    assert first.title == "Spacious 1 Bed/ 1 Bath Apartment Near UC Santa Barbara"
    assert first.address == "El Colegio Rd"
    assert first.city == "Isla Vista"
    assert first.beds == 1
    assert first.baths == 1
    assert first.kind == "sublease"
    assert first.rent_per_person == 2500
    assert first.rent is None
    assert first.rent_text == "Negotiable Rent $2,500"
    assert first.available == "3+ Months • Available Late Sep"
    assert "Room Type: Single" in first.amenities
    assert first.posted_at == "2026-09-23"
    assert first.geo_precision == "approx"
    assert first.photos[0].startswith("https://my-media-cdn.azureedge.net/photos/")


def test_detail_of_closed_lease_reports_closed():
    lst = Listing(id="myunistop:1762", source="myunistop", source_url="u", title="t", kind="lease")
    assert parse_detail((FIX / "myunistop_detail.html").read_text(), lst) == "closed"


def test_detail_login_wall_reports_wall():
    lst = Listing(id="myunistop:1", source="myunistop", source_url="u", title="t")
    assert parse_detail("<html><body>Sign in to continue</body></html>", lst) == "wall"


def test_detail_enriches_listing_when_open():
    html = (FIX / "myunistop_detail.html").read_text().replace("Leasing Closed", "Leasing Open")
    lst = Listing(id="myunistop:1762", source="myunistop", source_url="u", title="6710 Trigo Rd", kind="lease", address="Trigo Rd", geo_precision="approx")
    assert parse_detail(html, lst) == "ok"
    assert lst.address == "6710 Trigo Rd"
    assert lst.geo_precision is None
    assert lst.city == "Isla Vista"
    assert lst.rent == 9400
    assert lst.rent_per_person == 1050
    assert lst.beds == 4
    assert lst.baths == 2
    assert lst.available == "2027-28 School Year"
    assert lst.furnished == "Unfurnished (Bring your own furniture)"
    assert lst.laundry == "On-site laundry (at property)"
    assert lst.parking == "Paid parking available (extra cost)"
    assert lst.pets == "No pets allowed"
    assert lst.utilities_included == "Water · Trash"
    assert lst.manager.name == "Wolfe & Associates Property Services"
    assert "established in 1971" in lst.description
    assert len(lst.photos) >= 5
