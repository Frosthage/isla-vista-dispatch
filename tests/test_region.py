from scrape.geocode import classify_region, normalize_address


def test_del_playa_is_isla_vista():
    assert classify_region(34.4091772, -119.8569559) == "isla_vista"


def test_city_name_wins_without_coordinates():
    assert classify_region(None, None, "Isla Vista") == "isla_vista"


def test_downtown_santa_barbara_is_santa_barbara():
    assert classify_region(34.4208, -119.6982, "Santa Barbara") == "santa_barbara"


def test_goleta_outside_iv_is_santa_barbara():
    assert classify_region(34.4358, -119.8276, "Goleta") == "santa_barbara"


def test_los_angeles_is_dropped():
    assert classify_region(34.0522, -118.2437, "Los Angeles") is None


def test_normalize_strips_unit():
    assert normalize_address("6561 Del Playa, 5, Goleta, CA 93117") == "6561 Del Playa, Goleta, CA 93117"
    assert normalize_address("6657 El Colegio Rd # 19") == "6657 El Colegio Rd"
    assert normalize_address("6608 Sueno Road Apt A, Isla Vista") == "6608 Sueno Road, Isla Vista"
