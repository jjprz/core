"""Tests for the Spain fuel prices (Geoportal Gasolineras) config flow."""

from dataclasses import replace
from unittest.mock import AsyncMock

from aioprecioscarburantes import (
    PreciosCarburantesConnectionError,
    PreciosCarburantesNotFoundError,
    StationList,
)
import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.components.geoportal_gasolineras.const import (
    CONF_FUEL,
    CONF_MUNICIPALITY_ID,
    CONF_PROVINCE_ID,
    CONF_RADIUS,
    CONF_SHOW_ON_MAP,
    CONF_STATION_ID,
    DOMAIN,
    SUBENTRY_TYPE_STATION,
    SUBENTRY_TYPE_ZONE,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, FlowResultType

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def test_user_flow(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Test creating the entry, with a connection error and recovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    mock_client.get_provinces.side_effect = PreciosCarburantesConnectionError
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "cannot_connect"}

    mock_client.get_provinces.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Spain fuel prices"
    assert result["data"] == {}


async def test_single_instance(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test only one entry can be created."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def _start(hass: HomeAssistant, entry: MockConfigEntry, step: str) -> FlowResult:
    """Start adding a station and choose a menu option."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_STATION), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def _configure(result: FlowResult, hass: HomeAssistant, data: dict) -> FlowResult:
    return await hass.config_entries.subentries.async_configure(result["flow_id"], data)


@pytest.fixture
def empty_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return an entry without stations."""
    entry = MockConfigEntry(domain=DOMAIN, title="Spain fuel prices", data={})
    entry.add_to_hass(hass)
    return entry


async def test_add_from_list(
    hass: HomeAssistant, mock_client: AsyncMock, empty_entry: MockConfigEntry
) -> None:
    """Test adding a station from the list."""
    result = await _start(hass, empty_entry, "province")
    assert result["step_id"] == "province"
    result = await _configure(result, hass, {CONF_PROVINCE_ID: "41"})
    assert result["step_id"] == "municipality"
    mock_client.get_municipalities.assert_called_with("41")
    result = await _configure(result, hass, {CONF_MUNICIPALITY_ID: "6139"})
    assert result["step_id"] == "station"
    result = await _configure(result, hass, {CONF_STATION_ID: "7370"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(empty_entry.subentries.values()))
    assert subentry.title == "Repsol La Roda de Andalucía"
    assert subentry.unique_id == "7370"
    assert subentry.data == {
        CONF_PROVINCE_ID: "41",
        CONF_MUNICIPALITY_ID: "6139",
        CONF_STATION_ID: "7370",
        CONF_SHOW_ON_MAP: False,
    }


async def test_same_name_gets_address(
    hass: HomeAssistant, mock_client: AsyncMock, empty_entry: MockConfigEntry
) -> None:
    """Test a second station with the same name gets its address."""
    stations = mock_client.get_stations_by_municipality.return_value
    shell = stations.stations[1]
    mock_client.get_stations_by_municipality.return_value = StationList(
        updated_at=stations.updated_at,
        stations=[*stations.stations, type(shell)(**{**_fields(shell), "id": "1"})],
    )
    for station_id in ("6440", "1"):
        result = await _start(hass, empty_entry, "province")
        result = await _configure(result, hass, {CONF_PROVINCE_ID: "41"})
        result = await _configure(result, hass, {CONF_MUNICIPALITY_ID: "6139"})
        result = await _configure(result, hass, {CONF_STATION_ID: station_id})
    assert sorted(s.title for s in empty_entry.subentries.values()) == [
        "Shell La Roda de Andalucía",
        "Shell La Roda de Andalucía (Autovia Autovia A-92 Km. 123)",
    ]


def _fields(station: object) -> dict:
    return {name: getattr(station, name) for name in station.__slots__}  # type: ignore[attr-defined]


async def test_list_hides_added_stations(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test added stations are not offered again, and an empty list is an error."""
    mock_config_entry.add_to_hass(hass)
    result = await _start(hass, mock_config_entry, "province")
    result = await _configure(result, hass, {CONF_PROVINCE_ID: "41"})
    result = await _configure(result, hass, {CONF_MUNICIPALITY_ID: "6139"})
    options = result["data_schema"].schema[CONF_STATION_ID].config["options"]
    assert [option["value"] for option in options] == ["6440"]


@pytest.mark.parametrize(
    ("side_effect", "return_value", "reason"),
    [
        (PreciosCarburantesConnectionError, None, "cannot_connect"),
        (None, StationList(updated_at=None, stations=[]), "no_stations"),  # type: ignore[arg-type]
    ],
)
async def test_municipality_aborts(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    empty_entry: MockConfigEntry,
    side_effect: type[Exception] | None,
    return_value: StationList | None,
    reason: str,
) -> None:
    """Test the flow aborts when the stations cannot be listed."""
    mock_client.get_stations_by_municipality.side_effect = side_effect
    if return_value is not None:
        mock_client.get_stations_by_municipality.return_value = return_value
    result = await _start(hass, empty_entry, "province")
    result = await _configure(result, hass, {CONF_PROVINCE_ID: "41"})
    result = await _configure(result, hass, {CONF_MUNICIPALITY_ID: "6139"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


@pytest.mark.parametrize("method", ["get_provinces", "get_municipalities"])
async def test_list_abort_cannot_connect(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    empty_entry: MockConfigEntry,
    method: str,
) -> None:
    """Test adding from the list aborts when the lists cannot be fetched."""
    getattr(mock_client, method).side_effect = PreciosCarburantesConnectionError
    result = await _start(hass, empty_entry, "province")
    if result["type"] is FlowResultType.FORM:
        result = await _configure(result, hass, {CONF_PROVINCE_ID: "41"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_add_by_code(
    hass: HomeAssistant, mock_client: AsyncMock, empty_entry: MockConfigEntry
) -> None:
    """Test adding a station by its code, with errors and recovery."""
    result = await _start(hass, empty_entry, "station_code")
    assert result["step_id"] == "station_code"

    mock_client.get_station_by_id.side_effect = PreciosCarburantesNotFoundError
    result = await _configure(result, hass, {CONF_STATION_ID: "1"})
    assert result["errors"] == {"base": "station_not_found"}

    mock_client.get_station_by_id.side_effect = PreciosCarburantesConnectionError
    result = await _configure(result, hass, {CONF_STATION_ID: "9683"})
    assert result["errors"] == {"base": "cannot_connect"}

    mock_client.get_station_by_id.side_effect = None
    result = await _configure(result, hass, {CONF_STATION_ID: " 9683 "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(empty_entry.subentries.values()))
    assert subentry.title == "Cooperativa La Roda de Andalucía"
    assert subentry.data == {CONF_STATION_ID: "9683", CONF_SHOW_ON_MAP: False}
    mock_client.get_station_by_id.assert_called_with("9683")


async def test_add_by_code_already_added(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test a station from the list cannot be added again by code."""
    mock_config_entry.add_to_hass(hass)
    result = await _start(hass, mock_config_entry, "station_code")
    result = await _configure(result, hass, {CONF_STATION_ID: "7370"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_add_nearby(
    hass: HomeAssistant, mock_client: AsyncMock, empty_entry: MockConfigEntry
) -> None:
    """Test adding a station near home, closest first, with errors."""
    result = await _start(hass, empty_entry, "nearby")
    assert result["step_id"] == "nearby"

    mock_client.get_stations_by_province.side_effect = PreciosCarburantesConnectionError
    result = await _configure(result, hass, {CONF_PROVINCE_ID: "41", CONF_RADIUS: 10})
    assert result["errors"] == {"base": "cannot_connect"}

    mock_client.get_stations_by_province.side_effect = None
    stations = mock_client.get_stations_by_province.return_value
    mock_client.get_stations_by_province.return_value = StationList(
        updated_at=stations.updated_at, stations=stations.stations[1:]
    )
    # Only the Shell, which is 2.5 km away
    result = await _configure(result, hass, {CONF_PROVINCE_ID: "41", CONF_RADIUS: 1})
    assert result["errors"] == {"base": "no_stations_nearby"}

    # A station without coordinates is left out
    mock_client.get_stations_by_province.return_value = StationList(
        updated_at=stations.updated_at,
        stations=[
            *stations.stations,
            replace(stations.stations[0], id="1", latitude=None, longitude=None),
        ],
    )

    result = await _configure(result, hass, {CONF_PROVINCE_ID: "41", CONF_RADIUS: 10})
    assert result["step_id"] == "station"
    options = result["data_schema"].schema[CONF_STATION_ID].config["options"]
    assert [option["label"] for option in options] == [
        "Repsol – Carretera Malaga, Granada, Sevilla Km. 124,90, "
        "La Roda de Andalucía (0.0 km)",
        "Shell – Autovia Autovia A-92 Km. 123, La Roda de Andalucía (2.5 km)",
    ]
    result = await _configure(result, hass, {CONF_STATION_ID: "6440"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(empty_entry.subentries.values()))
    assert subentry.title == "Shell La Roda de Andalucía"
    assert subentry.data[CONF_MUNICIPALITY_ID] == "6139"


async def test_nearby_abort_cannot_connect(
    hass: HomeAssistant, mock_client: AsyncMock, empty_entry: MockConfigEntry
) -> None:
    """Test the nearby step aborts when the provinces cannot be fetched."""
    mock_client.get_provinces.side_effect = PreciosCarburantesConnectionError
    result = await _start(hass, empty_entry, "nearby")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_reconfigure(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test renaming a station and showing it on the map."""
    mock_config_entry.add_to_hass(hass)
    subentry = next(
        s for s in mock_config_entry.subentries.values() if s.unique_id == "9683"
    )
    result = await mock_config_entry.start_subentry_reconfigure_flow(
        hass, subentry.subentry_id
    )
    assert result["step_id"] == "reconfigure"
    result = await _configure(
        result, hass, {CONF_NAME: "Cooperativa", CONF_SHOW_ON_MAP: True}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    subentry = mock_config_entry.subentries[subentry.subentry_id]
    assert subentry.title == "Cooperativa"
    assert subentry.data == {CONF_STATION_ID: "9683", CONF_SHOW_ON_MAP: True}


async def test_add_zone(
    hass: HomeAssistant, mock_client: AsyncMock, empty_entry: MockConfigEntry
) -> None:
    """Test adding a zone, and the same zone again."""
    for expected in (FlowResultType.CREATE_ENTRY, FlowResultType.ABORT):
        result = await hass.config_entries.subentries.async_init(
            (empty_entry.entry_id, SUBENTRY_TYPE_ZONE), context={"source": SOURCE_USER}
        )
        assert result["step_id"] == "province"
        result = await _configure(result, hass, {CONF_PROVINCE_ID: "41"})
        result = await _configure(result, hass, {CONF_MUNICIPALITY_ID: "6139"})
        assert result["step_id"] == "fuel"
        result = await _configure(result, hass, {CONF_FUEL: "diesel_a"})
        assert result["type"] is expected
    zone = next(iter(empty_entry.subentries.values()))
    assert zone.title == "Gasoleo A – La Roda de Andalucía"
    assert zone.data == {
        CONF_PROVINCE_ID: "41",
        CONF_MUNICIPALITY_ID: "6139",
        CONF_FUEL: "diesel_a",
    }
