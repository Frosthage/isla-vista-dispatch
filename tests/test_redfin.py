from pathlib import Path

from scrape.sources.redfin import parse_page

FIX = Path(__file__).parent / "fixtures"


def test_isla_vista_search_page():
    listings = parse_page((FIX / "redfin_list.html").read_text())
    assert len(listings) == 56
    sky = next(l for l in listings if l.id == "redfin:21575448")
    assert sky.title == "Skyview Apartments"
    assert sky.source_url == "https://www.redfin.com/CA/Goleta/Skyview-Apartments/apartment/21575448"
    assert sky.rent == 2305
    assert sky.lat and sky.lng
    assert sky.photos[0] == "https://ssl.cdn-redfin.com/photo/rent/bafa3a43-a62f-47bb-92f5-bd5ba5cfa567/islphoto/genIsl.0_85.jpg"
    assert sky.photos[1] == "https://ssl.cdn-redfin.com/photo/rent/bafa3a43-a62f-47bb-92f5-bd5ba5cfa567/islphoto/genIsl.1_93.jpg"
    assert "Dishwasher" in sky.amenities
    first = next(l for l in listings if l.id == "redfin:21575047")
    assert first.address == "833 Embarcadero del Mar"
    assert first.city == "Goleta"
    assert first.beds == 1
    assert first.baths == 1
    assert first.description.startswith("Large one bedroom units in Isla Vista")
