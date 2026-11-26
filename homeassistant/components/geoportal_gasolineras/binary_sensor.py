"""Open or closed sensors for Spain fuel prices (Geoportal Gasolineras)."""

from datetime import datetime
from typing import override

from aioprecioscarburantes import Schedule, next_change, parse_schedule

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import CONF_STATION_ID, SUBENTRY_TYPE_STATION
from .coordinator import GeoportalGasolinerasConfigEntry
from .entity import StationEntity

# Coordinator is used to centralize the data updates
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoportalGasolinerasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up an open sensor for each station."""
    coordinator = entry.runtime_data
    for subentry in entry.get_subentries_of_type(SUBENTRY_TYPE_STATION):
        if subentry.data[CONF_STATION_ID] in coordinator.data.stations:
            async_add_entities(
                [OpenSensor(coordinator, subentry, "open")],
                config_subentry_id=subentry.subentry_id,
            )


class OpenSensor(StationEntity, BinarySensorEntity):
    """Whether the station is open, from its published opening hours."""

    _attr_translation_key = "open"
    _unsub_change: CALLBACK_TYPE | None = None

    def _schedule(self) -> Schedule | None:
        station = self.station
        return None if station is None else parse_schedule(station.schedule)

    @property
    @override
    def is_on(self) -> bool | None:
        """Return if open; None if the opening hours are not understood."""
        if (schedule := self._schedule()) is None:
            return None
        return schedule.is_open(dt_util.now())

    @override
    async def async_added_to_hass(self) -> None:
        """Schedule the next opening or closing."""
        await super().async_added_to_hass()
        self._schedule_next_change()

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Cancel the scheduled change."""
        await super().async_will_remove_from_hass()
        if self._unsub_change:
            self._unsub_change()
            self._unsub_change = None

    @override
    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the state and reschedule, the hours may have changed."""
        self._schedule_next_change()
        super()._handle_coordinator_update()

    @callback
    def _schedule_next_change(self) -> None:
        if self._unsub_change:
            self._unsub_change()
            self._unsub_change = None
        if (schedule := self._schedule()) is None:
            return
        if (moment := next_change(schedule, dt_util.now())) is not None:
            self._unsub_change = async_track_point_in_utc_time(
                self.hass, self._async_changed, dt_util.as_utc(moment)
            )

    @callback
    def _async_changed(self, _: datetime) -> None:
        """Write the new state at the opening or closing time."""
        self._unsub_change = None
        self._schedule_next_change()
        self.async_write_ha_state()
