"""Base entity for Spain fuel prices (Geoportal Gasolineras)."""

from typing import override

from aioprecioscarburantes import Station

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_STATION_ID, CONFIGURATION_URL, DOMAIN
from .coordinator import GeoportalGasolinerasCoordinator
from .names import brand_name, clean_address


class StationEntity(CoordinatorEntity[GeoportalGasolinerasCoordinator]):
    """An entity of a fuel station."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GeoportalGasolinerasCoordinator,
        subentry: ConfigSubentry,
        key: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._station_id: str = subentry.data[CONF_STATION_ID]
        station = coordinator.data[self._station_id]
        self._attr_unique_id = f"{self._station_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._station_id)},
            name=subentry.title,
            manufacturer=brand_name(station.brand),
            model=clean_address(station.address),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=CONFIGURATION_URL,
        )

    @property
    def station(self) -> Station | None:
        """Return the fetched station, if any."""
        return self.coordinator.data.get(self._station_id)

    @property
    @override
    def available(self) -> bool:
        """Return if the station was fetched."""
        return super().available and self.station is not None
