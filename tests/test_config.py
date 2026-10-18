"""What this deployment of the sidecar is, read from the environment.

`load_settings` takes its mapping as an argument so nothing here touches
os.environ.
"""

import pytest

from app.config import DEFAULT_PORT, DEFAULT_SITES, DEFAULT_SUBCATEGORY_IDS, BadLocation, load_settings


def test_an_empty_environment_serves_every_site_narrowed_to_games():
    settings = load_settings({})

    assert settings.sites == DEFAULT_SITES == ("es", "it", "pt")
    assert settings.port == DEFAULT_PORT
    assert settings.subcategory_ids == DEFAULT_SUBCATEGORY_IDS == ("10093", "24129")
    assert settings.locations == {}


def test_the_operator_can_pick_the_sites():
    assert load_settings({"WALLAPOP_SITES": " ES, it ,, "}).sites == ("es", "it")


def test_a_location_is_latitude_comma_longitude_as_maps_copies_it():
    settings = load_settings({"WALLAPOP_LOCATION_ES": "41.3874, 2.1686", "WALLAPOP_LOCATION_IT": "  "})

    assert settings.locations == {"es": (41.3874, 2.1686)}


@pytest.mark.parametrize("value", ["Barcelona", "41.3", "41.3,2.1,0", "91,0", "0,181", "nan,1"])
def test_a_location_that_is_not_a_point_stops_the_start_with_the_variable_named(value):
    with pytest.raises(BadLocation) as caught:
        load_settings({"WALLAPOP_LOCATION_ES": value})
    assert "WALLAPOP_LOCATION_ES" in str(caught.value)


def test_blank_values_fall_back_rather_than_configuring_nothing():
    settings = load_settings({"WALLAPOP_SITES": " ", "WALLAPOP_SUBCATEGORY_IDS": "", "PORT": ""})

    assert settings.sites == DEFAULT_SITES
    assert settings.subcategory_ids == DEFAULT_SUBCATEGORY_IDS
    assert settings.port == DEFAULT_PORT
