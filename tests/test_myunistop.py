from datetime import date
from pathlib import Path

from scrape.sources.myunistop import parse_list, parse_detail, _age_days

FIX = Path(__file__).parent / "fixtures"


def test_age_parsing():
    assert _age_days("57m ago") == 0
    assert _age_days("3d ago") == 3
    assert _age_days("2w ago") == 14
    assert _age_days("40w ago") == 280
    assert _age_days(None) is None


def test_list_cards_have_detail_paths_and_prices():
    cards = parse_list((FIX / "myunistop_list.html").read_text(), "lease")
    assert len(cards) >= 20
    first = cards[0]
    assert first["path"].startswith("/subleasedetail/2691/")
    assert first["title"] == "Spacious 1 Bed/ 1 Bath Apartment Near UC Santa Barbara"
    assert first["price"] == 2500
    assert first["age_days"] == 0
    assert first["type"] == "Sublease & Takeover"
    assert first["photos"][0].startswith("https://my-media-cdn.azureedge.net/photos/")


def test_detail_of_closed_lease_is_skipped():
    html = (FIX / "myunistop_detail.html").read_text()
    assert parse_detail(html, "/leasedetail/1762/x/", "lease", date(2026, 9, 23)) is None


def test_detail_fields_when_not_closed():
    html = (FIX / "myunistop_detail.html").read_text().replace("Leasing Closed", "Leasing Open")
    lst = parse_detail(html, "/leasedetail/1762/x/", "lease", date(2026, 9, 23))
    assert lst.id == "myunistop:1762"
    assert lst.address == "6710 Trigo Rd"
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
    assert lst.posted_at == "2025-12-17"
    assert len(lst.photos) >= 5
