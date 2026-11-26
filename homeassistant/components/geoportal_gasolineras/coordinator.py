"""Data update coordinator for Spain fuel prices (Geoportal Gasolineras)."""

import logging
from typing import override

from aioprecioscarburantes import (
    PreciosCarburantes,
    PreciosCarburantesError,
    PreciosCarburantesNotFoundError,
    Station,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_MUNICIPALITY_ID, CONF_STATION_ID, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type GeoportalGasolinerasConfigEntry = ConfigEntry[GeoportalGasolinerasCoordinator]


class GeoportalGasolinerasCoordinator(DataUpdateCoordinator[Station]):
    """Fetch the prices of one fuel station."""

    config_entry: GeoportalGasolinerasConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: GeoportalGasolinerasConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = PreciosCarburantes(session=async_get_clientsession(hass))
        self.municipality_id: str = config_entry.data[CONF_MUNICIPALITY_ID]
        self.station_id: str = config_entry.data[CONF_STATION_ID]

    @override
    async def _async_update_data(self) -> Station:
        """Fetch the station and its prices."""
        try:
            return await self.client.get_station(self.municipality_id, self.station_id)
        except PreciosCarburantesNotFoundError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="station_not_found",
                translation_placeholders={"station_id": self.station_id},
            ) from err
        except PreciosCarburantesError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
