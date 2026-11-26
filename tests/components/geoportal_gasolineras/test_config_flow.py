"""Tests for the Spain fuel prices (Geoportal Gasolineras) config flow."""

from unittest.mock import AsyncMock

from aioprecioscarburantes import PreciosCarburantesConnectionError, StationList
import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.components.geoportal_gasolineras.const import (
    CONF_MUNICIPALITY_ID,
    CONF_PROVINCE_ID,
    CONF_STATION_ID,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def _to_station_step(hass: HomeAssistant) -> str:
    """Go through the province and municipality steps."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROVINCE_ID: "41"}
    )
    assert result["step_id"] == "municipality"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MUNICIPALITY_ID: "6139"}
    )
    assert result["step_id"] == "station"
    return result["flow_id"]


async def test_full_flow(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Test choosing a station."""
    flow_id = await _to_station_step(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_STATION_ID: "6440"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Shell Roda De Andalucia (La)"
    assert result["result"].unique_id == "6440"
    assert result["data"] == {
        CONF_PROVINCE_ID: "41",
        CONF_MUNICIPALITY_ID: "6139",
        CONF_STATION_ID: "6440",
    }
    mock_client.get_municipalities.assert_called_with("41")


async def test_already_configured(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test a station can only be added once."""
    mock_config_entry.add_to_hass(hass)
    flow_id = await _to_station_step(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_STATION_ID: "7370"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize("method", ["get_provinces", "get_municipalities"])
async def test_abort_cannot_connect(
    hass: HomeAssistant, mock_client: AsyncMock, method: str
) -> None:
    """Test the flow aborts when the lists cannot be fetched."""
    getattr(mock_client, method).side_effect = PreciosCarburantesConnectionError
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    if result["type"] is FlowResultType.FORM:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PROVINCE_ID: "41"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.parametrize(
    ("side_effect", "return_value", "error"),
    [
        (PreciosCarburantesConnectionError, None, "cannot_connect"),
        (None, StationList(updated_at=None, stations=[]), "no_stations"),  # type: ignore[arg-type]
    ],
)
async def test_municipality_errors(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    side_effect: type[Exception] | None,
    return_value: StationList | None,
    error: str,
) -> None:
    """Test the municipality step shows errors and can recover."""
    stations = mock_client.get_stations_by_municipality.return_value
    mock_client.get_stations_by_municipality.side_effect = side_effect
    if return_value is not None:
        mock_client.get_stations_by_municipality.return_value = return_value
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROVINCE_ID: "41"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MUNICIPALITY_ID: "6139"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "municipality"
    assert result["errors"] == {"base": error}

    mock_client.get_stations_by_municipality.side_effect = None
    mock_client.get_stations_by_municipality.return_value = stations
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MUNICIPALITY_ID: "6139"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STATION_ID: "7370"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
