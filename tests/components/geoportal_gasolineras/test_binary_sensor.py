"""Tests for the open sensors of Spain fuel prices (Geoportal Gasolineras)."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.geoportal_gasolineras.const import SCAN_INTERVAL
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

REPSOL = "binary_sensor.repsol_la_roda_de_andalucia_open"
SHELL = "binary_sensor.shell_la_roda_de_andalucia_open"


@pytest.fixture(autouse=True)
async def thursday_noon(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Thursday 26 November 2026 at noon, Spanish time."""
    await hass.config.async_set_time_zone("Europe/Madrid")
    freezer.move_to("2026-11-26 11:00:00+00:00")


async def test_open_sensors(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test an open sensor is created for each station."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.geoportal_gasolineras.PLATFORMS",
        [Platform.BINARY_SENSOR],
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_opens_and_closes(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the state changes at the closing time, without waiting for a refresh."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    # Repsol: L-S 07:00-22:00; Shell: L-D 06:30-21:30
    assert hass.states.get(REPSOL).state == STATE_ON
    assert hass.states.get(SHELL).state == STATE_ON

    freezer.tick(timedelta(hours=9, minutes=29))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(SHELL).state == STATE_ON

    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(SHELL).state == STATE_OFF
    assert hass.states.get(REPSOL).state == STATE_ON


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
