from pathlib import Path

from scrape.sources.craigslist import parse_search, parse_detail

FIX = Path(__file__).parent / "fixtures"


def test_search_static_results():
    results = parse_search((FIX / "craigslist_search.html").read_text())
    assert len(results) == 22
    assert results[0]["url"] == "https://www.craigslist.org/view/d/santa-barbara-live-big-pay-less/bLXqCD17TRjQL8iAuBGMx9"
    assert results[0]["title"].startswith("Live Big, Pay Less!")
    assert results[0]["price"] == "$5,000"
    assert results[0]["location"] == "Santa Barbara"


def test_detail_fields():
    lst = parse_detail((FIX / "craigslist_detail.html").read_text(), "https://www.craigslist.org/view/d/santa-barbara-live-big-pay-less/bLXqCD17TRjQL8iAuBGMx9", "lease", "Santa Barbara")
    assert lst.id == "craigslist:bLXqCD17TRjQL8iAuBGMx9"
    assert lst.title == "Live Big, Pay Less! Spacious 2BR/2BA in Isla Vista — Just $1,000 PP!"
    assert lst.rent == 5000
    assert lst.beds == 2
    assert lst.baths == 2
    assert lst.sqft == 835
    assert lst.available == "now"
    assert lst.address == "6657 El Colegio Rd"
    assert lst.unit == "19"
    assert lst.lat == 34.417304
    assert lst.lng == -119.860420
    assert lst.geo_precision == "exact"
    assert lst.laundry == "laundry on site"
    assert lst.parking == "off-street parking"
    assert "apartment" in lst.amenities
    assert lst.description.startswith("More roommates. More space.")
    assert lst.photos[0] == "https://images.craigslist.org/00H0H_2wFxWxaDXF2_0CI0pO_1200x900.jpg"
    assert lst.posted_at == "2026-09-03T10:28:02-0700"
    assert lst.kind == "lease"
