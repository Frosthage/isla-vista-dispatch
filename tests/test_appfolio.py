from pathlib import Path

from scrape.sources.appfolio import parse_list

FIX = Path(__file__).parent / "fixtures"


def test_playalifeiv_list_parses_all_cards_with_coordinates():
    listings = parse_list((FIX / "appfolio_list_playalifeiv.html").read_text(), "playalifeiv")
    assert len(listings) == 68
    first = listings[0]
    assert first.id == "appfolio:playalifeiv:7cd6329e-6c5c-487a-96d3-121603c61730"
    assert first.source_url == "https://playalifeiv.appfolio.com/listings/detail/7cd6329e-6c5c-487a-96d3-121603c61730"
    assert first.address == "6561 Del Playa"
    assert first.unit == "5"
    assert first.city == "Goleta"
    assert first.zip == "93117"
    assert first.rent == 7000
    assert first.beds == 2
    assert first.baths == 2
    assert first.available == "2027-2028"
    assert first.lat == 34.409106
    assert first.lng == -119.856902
    assert first.geo_precision == "exact"
    assert first.utilities_included == "Water, Landscaping, Trash"
    assert first.pets == "Cats not allowed, Dogs not allowed"
    assert first.photos == ["https://images.cdn.appfolio.com/playalifeiv/images/175977d4-3230-4bfe-a456-55315eb43e1a/large.jpg"]
    assert first.manager.name == "Playa Life IV"
    assert "Oceanside Living" in first.description
