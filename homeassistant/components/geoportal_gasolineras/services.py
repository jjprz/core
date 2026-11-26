"""Actions for Spain fuel prices (Geoportal Gasolineras)."""

from typing import Any, cast

from aioprecioscarburantes import FuelType, parse_schedule
import probatio

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import CONF_FUEL, CONF_STATION_ID, DOMAIN, SUBENTRY_TYPE_STATION
from .coordinator import GeoportalGasolinerasConfigEntry
from .names import clean_address, municipality_name

SERVICE_GET_PRICES = "get_prices"

GET_PRICES_SCHEMA = probatio.Schema(
    {
        probatio.Optional(CONF_FUEL): probatio.In(
            [fuel.name.lower() for fuel in FuelType]
        )
    }
)


async def _async_get_prices(call: ServiceCall) -> ServiceResponse:
    """Return the prices of the configured stations."""
    entries: list[GeoportalGasolinerasConfigEntry] = (
        call.hass.config_entries.async_loaded_entries(DOMAIN)
    )
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    entry = entries[0]
    data = entry.runtime_data.data
    fuel = FuelType[call.data[CONF_FUEL].upper()] if CONF_FUEL in call.data else None
    now = dt_util.now()

    stations: list[dict[str, Any]] = []
    for subentry in entry.get_subentries_of_type(SUBENTRY_TYPE_STATION):
        station = data.stations.get(subentry.data[CONF_STATION_ID])
        if station is None or (fuel is not None and fuel not in station.prices):
            continue
        schedule = parse_schedule(station.schedule)
        item: dict[str, Any] = {
            "name": subentry.title,
            "station_id": station.id,
            "address": clean_address(station.address),
            "municipality": municipality_name(station.municipality),
            "open": None if schedule is None else schedule.is_open(now),
        }
        if fuel is None:
            item["prices"] = {
                key.name.lower(): price for key, price in station.prices.items()
            }
        else:
            item["price"] = station.prices[fuel]
        stations.append(item)
    if fuel is not None:
        stations.sort(key=lambda item: item["price"])
    return cast(ServiceResponse, {"stations": stations})


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PRICES,
        _async_get_prices,
        schema=GET_PRICES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
