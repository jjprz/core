"""Tests for the Spain fuel prices (Geoportal Gasolineras) sensors."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

from aioprecioscarburantes import FuelType, PreciosCarburantesConnectionError
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.geoportal_gasolineras.const import SCAN_INTERVAL
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

REPSOL_DIESEL = "sensor.repsol_la_roda_de_andalucia_diesel_a"
REPSOL_E5 = "sensor.repsol_la_roda_de_andalucia_gasoline_95_e5"
COOPERATIVA_DIESEL_B = "sensor.cooperativa_la_roda_de_andalucia_diesel_b"
ZONE = "sensor.gasoleo_a_la_roda_de_andalucia"


@pytest.mark.parametrize("platform", [Platform.SENSOR, Platform.BINARY_SENSOR])
async def test_entities(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    platform: Platform,
) -> None:
    """Test the entities of the stations and the zone."""
    mock_config_entry.add_to_hass(hass)
    with patch("homeassistant.components.geoportal_gasolineras.PLATFORMS", [platform]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_zone(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test the lowest price, average and cheapest station of a zone."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(f"{ZONE}_lowest_price").state == "1.825"
    assert hass.states.get(f"{ZONE}_average_price").state == "1.855"
    cheapest = hass.states.get(f"{ZONE}_cheapest_station")
    assert cheapest.state == "Repsol – Carretera Malaga, Granada, Sevilla Km. 124,90"
    assert cheapest.attributes["station_id"] == "7370"
    assert cheapest.attributes["stations"] == 2


async def test_updates(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test dropped fuels, new fuels, missing stations and errors."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(REPSOL_DIESEL).state == "1.825"

    # Nobody sells diesel A any more and the Repsol starts selling LPG
    stations = mock_client.get_stations_by_municipality.return_value
    changed = []
    for station in stations.stations:
        prices = {k: v for k, v in station.prices.items() if k is not FuelType.DIESEL_A}
        prices[FuelType.LPG] = 0.999
        changed.append(replace(station, prices=prices))
    mock_client.get_stations_by_municipality.return_value = replace(
        stations, stations=changed
    )
    await _tick(hass, freezer)
    assert hass.states.get(REPSOL_DIESEL).state == STATE_UNAVAILABLE
    assert hass.states.get(f"{ZONE}_lowest_price").state == STATE_UNAVAILABLE
    assert hass.states.get(REPSOL_E5).state == "1.575"
    assert hass.states.get("sensor.repsol_la_roda_de_andalucia_lpg").state == "0.999"

    # The cooperative cannot be fetched: only its entities become unavailable
    mock_client.get_station_by_id.side_effect = PreciosCarburantesConnectionError
    await _tick(hass, freezer)
    assert hass.states.get(COOPERATIVA_DIESEL_B).state == STATE_UNAVAILABLE
    assert hass.states.get(REPSOL_E5).state == "1.575"

    # Nothing can be fetched
    mock_client.get_stations_by_municipality.side_effect = (
        PreciosCarburantesConnectionError
    )
    await _tick(hass, freezer)
    assert hass.states.get(REPSOL_E5).state == STATE_UNAVAILABLE
