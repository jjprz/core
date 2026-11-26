"""Data update coordinator for Spain fuel prices (Geoportal Gasolineras)."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import override

from aioprecioscarburantes import (
    PreciosCarburantes,
    PreciosCarburantesError,
    PreciosCarburantesNotFoundError,
    Station,
)

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_MUNICIPALITY_ID,
    CONF_STATION_ID,
    DOMAIN,
    SCAN_INTERVAL,
    SUBENTRY_TYPE_STATION,
    SUBENTRY_TYPE_ZONE,
)

_LOGGER = logging.getLogger(__name__)

type GeoportalGasolinerasConfigEntry = ConfigEntry[GeoportalGasolinerasCoordinator]


@dataclass
class GeoportalGasolinerasData:
    """Fetched stations."""

    # Configured stations by id
    stations: dict[str, Station] = field(default_factory=dict)
    # When the Ministry published the prices of a station from the official list
    updated_at: dict[str, datetime] = field(default_factory=dict)
    # All stations of the municipalities of the zones
    municipalities: dict[str, list[Station]] = field(default_factory=dict)


def removed_issue_id(subentry: ConfigSubentry) -> str:
    """Return the id of the repair issue of a station that disappeared."""
    return f"station_removed_{subentry.subentry_id}"


class GeoportalGasolinerasCoordinator(DataUpdateCoordinator[GeoportalGasolinerasData]):
    """Fetch the prices of all configured fuel stations and zones."""

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

    @override
    async def _async_update_data(self) -> GeoportalGasolinerasData:
        """Fetch the stations, one request per municipality.

        Stations added by code have no municipality; they are read from the
        Geoportal web, which also lists stations with restricted sales. A station
        that cannot be fetched is left out, so only its entities become unavailable.
        """
        entry = self.config_entry
        stations = entry.get_subentries_of_type(SUBENTRY_TYPE_STATION)
        zones = entry.get_subentries_of_type(SUBENTRY_TYPE_ZONE)
        by_municipality: defaultdict[str, list[ConfigSubentry]] = defaultdict(list)
        by_code: list[ConfigSubentry] = []
        for subentry in stations:
            if municipality_id := subentry.data.get(CONF_MUNICIPALITY_ID):
                by_municipality[municipality_id].append(subentry)
            else:
                by_code.append(subentry)
        zone_municipalities = {zone.data[CONF_MUNICIPALITY_ID] for zone in zones}

        data = GeoportalGasolinerasData()
        requests = failed = 0
        for municipality_id in by_municipality.keys() | zone_municipalities:
            requests += 1
            try:
                result = await self.client.get_stations_by_municipality(municipality_id)
            except PreciosCarburantesError as err:
                _LOGGER.debug("Cannot fetch municipality %s: %s", municipality_id, err)
                failed += 1
                continue
            listed = {station.id: station for station in result.stations}
            if municipality_id in zone_municipalities:
                data.municipalities[municipality_id] = result.stations
            for subentry in by_municipality.get(municipality_id, []):
                station_id = subentry.data[CONF_STATION_ID]
                if station := listed.get(station_id):
                    data.stations[station_id] = station
                    data.updated_at[station_id] = result.updated_at
                self._update_removed_issue(subentry, removed=station is None)
        for subentry in by_code:
            requests += 1
            station_id = subentry.data[CONF_STATION_ID]
            try:
                data.stations[station_id] = await self.client.get_station_by_id(
                    station_id
                )
            except PreciosCarburantesNotFoundError:
                self._update_removed_issue(subentry, removed=True)
            except PreciosCarburantesError as err:
                _LOGGER.debug("Cannot fetch station %s: %s", station_id, err)
                failed += 1
            else:
                self._update_removed_issue(subentry, removed=False)

        if failed and failed == requests:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            )
        return data

    def _update_removed_issue(self, subentry: ConfigSubentry, *, removed: bool) -> None:
        """Offer to delete a station that is no longer listed."""
        issue_id = removed_issue_id(subentry)
        if not removed:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="station_removed",
            translation_placeholders={"name": subentry.title},
            data={
                "entry_id": self.config_entry.entry_id,
                "subentry_id": subentry.subentry_id,
            },
        )
