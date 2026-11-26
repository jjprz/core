"""Fuel price sensors for Spain fuel prices (Geoportal Gasolineras)."""

from typing import override

from aioprecioscarburantes import FuelType

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CURRENCY_EURO, UnitOfMass, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_STATION_ID, SUBENTRY_TYPE_STATION
from .coordinator import (
    GeoportalGasolinerasConfigEntry,
    GeoportalGasolinerasCoordinator,
)
from .entity import StationEntity

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

FUEL_SENSORS: dict[FuelType, SensorEntityDescription] = {
    fuel: SensorEntityDescription(
        key=fuel.name.lower(),
        translation_key=fuel.name.lower(),
        native_unit_of_measurement=(
            f"{CURRENCY_EURO}/{UnitOfMass.KILOGRAMS}"
            if fuel in FUELS_PER_KG
            else f"{CURRENCY_EURO}/{UnitOfVolume.LITERS}"
        ),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
    )
    for fuel in FuelType
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoportalGasolinerasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a price sensor for each fuel each station sells."""
    coordinator = entry.runtime_data
    added: set[tuple[str, FuelType]] = set()

    @callback
    def async_add_sensors() -> None:
        """Add sensors for stations and fuels not seen before."""
        for subentry in entry.get_subentries_of_type(SUBENTRY_TYPE_STATION):
            station_id: str = subentry.data[CONF_STATION_ID]
            if (station := coordinator.data.get(station_id)) is None:
                continue
            new = [fuel for fuel in station.prices if (station_id, fuel) not in added]
            added.update((station_id, fuel) for fuel in new)
            if new:
                async_add_entities(
                    (FuelPriceSensor(coordinator, subentry, fuel) for fuel in new),
                    config_subentry_id=subentry.subentry_id,
                )

    async_add_sensors()
    entry.async_on_unload(coordinator.async_add_listener(async_add_sensors))


class FuelPriceSensor(StationEntity, SensorEntity):
    """Price of one fuel at a station."""

    def __init__(
        self,
        coordinator: GeoportalGasolinerasCoordinator,
        subentry: ConfigSubentry,
        fuel: FuelType,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = FUEL_SENSORS[fuel]
        super().__init__(coordinator, subentry, self.entity_description.key)
        self._fuel = fuel

    @property
    @override
    def available(self) -> bool:
        """Return if the station was fetched and still sells this fuel."""
        station = self.station
        return (
            super().available and station is not None and self._fuel in station.prices
        )

    @property
    @override
    def native_value(self) -> float:
        """Return the price; only called while available."""
        return self.coordinator.data[self._station_id].prices[self._fuel]
