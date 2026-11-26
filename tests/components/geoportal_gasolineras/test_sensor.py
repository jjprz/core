"""Tests for the Spain fuel prices (Geoportal Gasolineras) sensors."""

from dataclasses import replace
from unittest.mock import AsyncMock

from aioprecioscarburantes import FuelType, PreciosCarburantesConnectionError
from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.geoportal_gasolineras.const import SCAN_INTERVAL
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


async def test_sensors(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test a sensor is created for each fuel the station sells."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_unavailable(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test sensors become unavailable on errors and when a fuel is dropped."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = "sensor.repsol_roda_de_andalucia_la_diesel_a"
    assert hass.states.get(entity_id).state == "1.825"

    station = mock_client.get_station.return_value
    mock_client.get_station.return_value = replace(
        station,
        prices={k: v for k, v in station.prices.items() if k is not FuelType.DIESEL_A},
    )
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    assert (
        hass.states.get("sensor.repsol_roda_de_andalucia_la_gasoline_95_e5").state
        == "1.575"
    )

    mock_client.get_station.side_effect = PreciosCarburantesConnectionError
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.repsol_roda_de_andalucia_la_gasoline_95_e5").state
        == STATE_UNAVAILABLE
    )
