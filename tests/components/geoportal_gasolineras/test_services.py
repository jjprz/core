"""Tests for the actions of Spain fuel prices (Geoportal Gasolineras)."""

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.components.geoportal_gasolineras.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component


async def test_get_prices(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test all prices, and one fuel cheapest first."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    response = await hass.services.async_call(
        DOMAIN, "get_prices", {}, blocking=True, return_response=True
    )
    assert response == {
        "stations": [
            {
                "name": "Repsol La Roda de Andalucía",
                "station_id": "7370",
                "address": "Carretera Malaga, Granada, Sevilla Km. 124,90",
                "municipality": "Roda de Andalucía (La)",
                "open": True,
                "prices": {
                    "diesel_a": 1.825,
                    "diesel_premium": 1.875,
                    "gasoline_95_e5": 1.575,
                },
            },
            {
                "name": "Cooperativa La Roda de Andalucía",
                "station_id": "9683",
                "address": "Carretera De Pedrera Km. 2",
                "municipality": "Roda de Andalucía (La)",
                "open": True,
                "prices": {"diesel_a": 1.802, "diesel_b": 1.477},
            },
        ]
    }

    response = await hass.services.async_call(
        DOMAIN, "get_prices", {"fuel": "diesel_a"}, blocking=True, return_response=True
    )
    assert response is not None
    assert [(s["station_id"], s["price"]) for s in response["stations"]] == [  # type: ignore[union-attr,index]
        ("9683", 1.802),
        ("7370", 1.825),
    ]


async def test_get_prices_not_loaded(hass: HomeAssistant) -> None:
    """Test the action fails when the integration is not set up."""
    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "get_prices", {}, blocking=True, return_response=True
        )


async def test_get_prices_skips_stations_without_fuel(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test stations not selling the fuel are left out."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    response = await hass.services.async_call(
        DOMAIN, "get_prices", {"fuel": "diesel_b"}, blocking=True, return_response=True
    )
    assert response is not None
    assert [s["station_id"] for s in response["stations"]] == ["9683"]  # type: ignore[union-attr,index]
