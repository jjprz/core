"""Tests for setting up Spain fuel prices (Geoportal Gasolineras)."""

from unittest.mock import AsyncMock

from aioprecioscarburantes import PreciosCarburantesConnectionError
from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components.geoportal_gasolineras.const import (
    CONF_MUNICIPALITY_ID,
    CONF_STATION_ID,
    SCAN_INTERVAL,
    SUBENTRY_TYPE_STATION,
)
from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant


async def test_setup_and_unload(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test one request per municipality, shared by stations and zones."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_client.get_stations_by_municipality.assert_called_once_with("6139")
    mock_client.get_station_by_id.assert_called_once_with("9683")

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_when_all_fail(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test setup is retried when nothing can be fetched."""
    mock_client.get_stations_by_municipality.side_effect = (
        PreciosCarburantesConnectionError
    )
    mock_client.get_station_by_id.side_effect = PreciosCarburantesConnectionError
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_partial_failure(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a station that cannot be fetched does not stop the others."""
    mock_client.get_station_by_id.side_effect = PreciosCarburantesConnectionError
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.repsol_la_roda_de_andalucia_diesel_a")
    assert hass.states.get("sensor.cooperativa_la_roda_de_andalucia_diesel_a") is None
    assert (
        hass.states.get("binary_sensor.cooperativa_la_roda_de_andalucia_open") is None
    )

    # It comes back: all its entities are added
    mock_client.get_station_by_id.side_effect = None
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.cooperativa_la_roda_de_andalucia_diesel_a")
    assert (
        hass.states.get("binary_sensor.cooperativa_la_roda_de_andalucia_open").state
        == "on"
    )


async def test_reload_on_new_station(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test adding a station reloads the entry and creates its entities."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    hass.config_entries.async_add_subentry(
        mock_config_entry,
        ConfigSubentry(
            subentry_type=SUBENTRY_TYPE_STATION,
            title="Shell La Roda de Andalucía",
            unique_id="6440",
            data={CONF_MUNICIPALITY_ID: "6139", CONF_STATION_ID: "6440"},
        ),
    )
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.shell_la_roda_de_andalucia_diesel_a").state == "1.885"
    )
    assert (
        hass.states.get("binary_sensor.shell_la_roda_de_andalucia_open").state == "on"
    )
