from pathlib import Path

from scrape.sources.meridian import parse_list, parse_detail

FIX = Path(__file__).parent / "fixtures"


def test_list_properties():
    props = parse_list((FIX / "meridian_list.html").read_text())
    assert len(props) == 5
    assert props[0]["url"] == "https://meridiangrouprem.com/properties/6547-cordoba-road/"
    assert props[0]["street"] == "6547 Cordoba Road"
    assert props[0]["city"] == "Goleta"
    assert props[0]["zip"] == "93117"
    assert props[0]["propid"] == "7056"
    assert props[0]["image"].startswith("https://rm12filereader.rentmanager.com/files/get/?EID=mgrem&FKey=")


def test_detail_units():
    prop = {"url": "https://meridiangrouprem.com/properties/6643-abrego-road/", "propid": "7001", "street": "6643 Abrego Road", "city": "Goleta", "zip": "93117", "image": None}
    units = parse_detail((FIX / "meridian_detail.html").read_text(), prop)
    assert len(units) == 2
    u = units[0]
    assert u.id == "meridian:7001-F3"
    assert u.title == "6643 Abrego Road #F3"
    assert u.unit == "F3"
    assert u.rent == 4500
    assert u.beds == 2
    assert u.baths == 1.5
    assert u.sqft is None
    assert u.available == "09/21/2026"
    assert u.source_url == "https://meridiangrouprem.com/units/f3/"
    assert u.amenities == ["Laundry On-Site", "Off Street Parking"]
    assert u.photos and "rentmanager.com" in u.photos[0]
    assert u.manager.name == "Meridian Group"
