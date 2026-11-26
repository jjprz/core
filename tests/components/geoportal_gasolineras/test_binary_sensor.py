"""Tests for the open sensors of Spain fuel prices (Geoportal Gasolineras)."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components.geoportal_gasolineras.const import SCAN_INTERVAL
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

REPSOL = "binary_sensor.repsol_la_roda_de_andalucia_open"
COOPERATIVA = "binary_sensor.cooperativa_la_roda_de_andalucia_open"


async def test_opens_and_closes(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the state changes at the closing time, without a refresh."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(REPSOL).state == STATE_ON
    assert hass.states.get(COOPERATIVA).state == STATE_ON  # 24H

    # The Repsol closes at 22:00, ten hours later; refreshes happen meanwhile
    freezer.tick(timedelta(hours=9, minutes=59))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(REPSOL).state == STATE_ON
    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(REPSOL).state == STATE_OFF
    assert hass.states.get(COOPERATIVA).state == STATE_ON


async def test_unknown_hours(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test opening hours that are not understood give an unknown state."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    stations = mock_client.get_stations_by_municipality.return_value
    mock_client.get_stations_by_municipality.return_value = replace(
        stations,
        stations=[replace(s, schedule="L: 24H") for s in stations.stations],
    )
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(REPSOL).state == STATE_UNKNOWN

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
