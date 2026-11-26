"""Fuel price sensors for Spain fuel prices (Geoportal Gasolineras)."""

from typing import override

from aioprecioscarburantes import FuelType

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import CURRENCY_EURO, UnitOfMass, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import (
    GeoportalGasolinerasConfigEntry,
    GeoportalGasolinerasCoordinator,
)

# Coordinator is used to centralize the data updates
PARALLEL_UPDATES = 0

# Fuels sold by weight; the rest are sold by volume
FUELS_PER_KG = {
    FuelType.AMMONIA,
    FuelType.COMPRESSED_BIOGAS,
    FuelType.LIQUEFIED_BIOGAS,
    FuelType.COMPRESSED_NATURAL_GAS,
    FuelType.LIQUEFIED_NATURAL_GAS,
    FuelType.HYDROGEN,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoportalGasolinerasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a price sensor for each fuel the station sells."""
    coordinator = entry.runtime_data
    async_add_entities(
        FuelPriceSensor(coordinator, fuel) for fuel in coordinator.data.prices
    )


class FuelPriceSensor(CoordinatorEntity[GeoportalGasolinerasCoordinator], SensorEntity):
    """Price of one fuel at a station."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3

    def __init__(
        self, coordinator: GeoportalGasolinerasCoordinator, fuel: FuelType
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._fuel = fuel
        station = coordinator.data
        self._attr_translation_key = fuel.name.lower()
        self._attr_unique_id = f"{station.id}_{fuel.name.lower()}"
        unit = UnitOfMass.KILOGRAMS if fuel in FUELS_PER_KG else UnitOfVolume.LITERS
        self._attr_native_unit_of_measurement = f"{CURRENCY_EURO}/{unit}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, station.id)},
            name=f"{station.brand.title()} {station.locality.title()}",
            manufacturer=station.brand.title(),
            model=station.address.title(),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://geoportalgasolineras.es/",
        )

    @property
    @override
    def available(self) -> bool:
        """Return if the station still sells this fuel."""
        return super().available and self._fuel in self.coordinator.data.prices

    @property
    @override
    def native_value(self) -> float | None:
        """Return the price."""
        return self.coordinator.data.prices.get(self._fuel)
