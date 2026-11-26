"""Fixtures for the Spain fuel prices (Geoportal Gasolineras) tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

from aioprecioscarburantes import Municipality, Province, Station, StationList
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    load_json_array_fixture,
    load_json_object_fixture,
)

from homeassistant.components.geoportal_gasolineras.const import (
    CONF_FUEL,
    CONF_MUNICIPALITY_ID,
    CONF_PROVINCE_ID,
    CONF_SHOW_ON_MAP,
    CONF_STATION_ID,
    DOMAIN,
    SUBENTRY_TYPE_STATION,
    SUBENTRY_TYPE_ZONE,
)
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the entry with a station from the list and one added by code."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Spain fuel prices",
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_STATION,
                title="Repsol La Roda de Andalucía",
                unique_id="7370",
                data={
                    CONF_PROVINCE_ID: "41",
                    CONF_MUNICIPALITY_ID: "6139",
                    CONF_STATION_ID: "7370",
                    CONF_SHOW_ON_MAP: True,
                },
            ),
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_STATION,
                title="Cooperativa La Roda de Andalucía",
                unique_id="9683",
                data={CONF_STATION_ID: "9683", CONF_SHOW_ON_MAP: False},
            ),
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_ZONE,
                title="Gasoleo A – La Roda de Andalucía",
                unique_id="6139_diesel_a",
                data={
                    CONF_PROVINCE_ID: "41",
                    CONF_MUNICIPALITY_ID: "6139",
                    CONF_FUEL: "diesel_a",
                },
            ),
        ],
    )


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Do not set up the entry in config flow tests."""
    with patch(
        "homeassistant.components.geoportal_gasolineras.async_setup_entry",
        return_value=None,
    ) as mock:
        yield mock


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """Mock the API client."""
    stations = StationList.from_api(load_json_object_fixture("estaciones.json", DOMAIN))
    with (
        patch(
            "homeassistant.components.geoportal_gasolineras.coordinator.PreciosCarburantes",
            autospec=True,
        ) as client_class,
        patch(
            "homeassistant.components.geoportal_gasolineras.config_flow.PreciosCarburantes",
            new=client_class,
        ),
    ):
        client = client_class.return_value
        client.get_provinces.return_value = [
            Province.from_api(item)
            for item in load_json_array_fixture("provincias.json", DOMAIN)
        ]
        client.get_municipalities.return_value = [
            Municipality.from_api(item)
            for item in load_json_array_fixture("municipios.json", DOMAIN)
        ]
        client.get_stations_by_municipality.return_value = stations
        client.get_stations_by_province.return_value = stations
        client.get_station_by_id.return_value = Station.from_geoportal(
            load_json_object_fixture("geoportal_estacion.json", DOMAIN)
        )
        yield client


@pytest.fixture(autouse=True)
def frozen_time(freezer: FrozenDateTimeFactory) -> None:
    """Thursday 26 November 2026 at noon, Spanish time."""
    freezer.move_to("2026-11-26 11:00:00+00:00")


@pytest.fixture(autouse=True)
async def home(hass: HomeAssistant) -> None:
    """Put home at the Repsol station (public data)."""
    await hass.config.async_update(
        latitude=37.214444, longitude=-4.777056, time_zone="Europe/Madrid"
    )
