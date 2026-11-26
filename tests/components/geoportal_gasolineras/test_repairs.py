"""Tests for the repairs of Spain fuel prices (Geoportal Gasolineras)."""

from dataclasses import replace
from unittest.mock import AsyncMock

from aioprecioscarburantes import PreciosCarburantesNotFoundError
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components.geoportal_gasolineras.const import DOMAIN, SCAN_INTERVAL
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component


def _subentry_id(entry: MockConfigEntry, unique_id: str) -> str:
    return next(
        s.subentry_id for s in entry.subentries.values() if s.unique_id == unique_id
    )


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _remove(mock_client: AsyncMock, unique_id: str) -> None:
    """Make a station disappear from the official list or the Geoportal web."""
    if unique_id == "7370":
        stations = mock_client.get_stations_by_municipality.return_value
        mock_client.get_stations_by_municipality.return_value = replace(
            stations, stations=stations.stations[1:]
        )
    else:
        mock_client.get_station_by_id.side_effect = PreciosCarburantesNotFoundError


@pytest.mark.parametrize("unique_id", ["7370", "9683"])
async def test_issue_comes_and_goes(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
    freezer: FrozenDateTimeFactory,
    unique_id: str,
) -> None:
    """Test the issue appears when a station disappears and goes when it returns."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    issue_id = f"station_removed_{_subentry_id(mock_config_entry, unique_id)}"
    stations = mock_client.get_stations_by_municipality.return_value

    _remove(mock_client, unique_id)
    await _tick(hass, freezer)
    assert issue_registry.async_get_issue(DOMAIN, issue_id)

    mock_client.get_stations_by_municipality.return_value = stations
    mock_client.get_station_by_id.side_effect = None
    await _tick(hass, freezer)
    assert not issue_registry.async_get_issue(DOMAIN, issue_id)


async def test_fix_removes_station(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the station is removed from Repairs, or the flow aborts if gone."""
    assert await async_setup_component(hass, "repairs", {})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    subentry_id = _subentry_id(mock_config_entry, "9683")
    _remove(mock_client, "9683")
    await _tick(hass, freezer)

    manager = repairs_flow_manager(hass)
    assert manager is not None
    issue_id = f"station_removed_{subentry_id}"
    result = await manager.async_init(DOMAIN, data={"issue_id": issue_id})
    assert result["step_id"] == "confirm"
    result = await manager.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert subentry_id not in mock_config_entry.subentries


async def test_stale_issue(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test an issue of a station removed by hand aborts and is cleaned up."""
    assert await async_setup_component(hass, "repairs", {})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    ir.async_create_issue(
        hass,
        DOMAIN,
        "station_removed_gone",
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="station_removed",
        translation_placeholders={"name": "Gone"},
        data={"entry_id": mock_config_entry.entry_id, "subentry_id": "gone"},
    )
    manager = repairs_flow_manager(hass)
    assert manager is not None
    result = await manager.async_init(DOMAIN, data={"issue_id": "station_removed_gone"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "station_already_removed"

    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    assert not issue_registry.async_get_issue(DOMAIN, "station_removed_gone")
