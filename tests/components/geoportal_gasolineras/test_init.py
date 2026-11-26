"""Tests for setting up Spain fuel prices (Geoportal Gasolineras)."""

from unittest.mock import AsyncMock

from aioprecioscarburantes import (
    PreciosCarburantesConnectionError,
    PreciosCarburantesNotFoundError,
)
import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant


async def test_setup_and_unload(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test the entry is set up and unloaded."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_client.get_station.assert_called_with("6139", "7370")

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    "side_effect",
    [PreciosCarburantesConnectionError, PreciosCarburantesNotFoundError],
)
async def test_setup_retry(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    side_effect: type[Exception],
) -> None:
    """Test setup is retried when the station cannot be fetched."""
    mock_client.get_station.side_effect = side_effect
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_by_code(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry_by_code: MockConfigEntry,
) -> None:
    """Test a station added by code is read from the Geoportal web."""
    mock_config_entry_by_code.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry_by_code.entry_id)
    mock_client.get_station_by_id.assert_called_with("9683")
    mock_client.get_station.assert_not_called()
    assert (
        hass.states.get("sensor.cooperativa_roda_de_andalucia_la_diesel_b").state
        == "1.477"
    )
