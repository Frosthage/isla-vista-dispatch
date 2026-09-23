from pathlib import Path

from scrape.sources.apartmentguide import parse_page

FIX = Path(__file__).parent / "fixtures"


def test_isla_vista_page():
    listings = parse_page((FIX / "apartmentguide_list.html").read_text())
    assert len(listings) >= 40
    bp = next(l for l in listings if l.title == "Breakpointe Coronado")
    assert bp.id == "apartmentguide:6774750"
    assert bp.source_url == "https://www.apartmentguide.com/a/Breakpointe-Coronado-Goleta-CA-6774750/"
    assert bp.address == "6672 Abrego Rd"
    assert bp.city == "Goleta"
    assert bp.zip == "93117"
    assert bp.lat == 34.414623
    assert bp.lng == -119.86153
    assert bp.rent == 1330
    assert bp.beds == 0
    assert len(bp.photos) > 5
    assert bp.photos[0] == "https://i.apartmentguide.com/t_3x2_fixed_webp_md/33a64e0995025c423ba8c17f07b223d3"
