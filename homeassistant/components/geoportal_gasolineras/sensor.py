"""Sensors for Spain fuel prices (Geoportal Gasolineras)."""

from datetime import datetime
from statistics import mean
from typing import Any, override

from aioprecioscarburantes import FuelType, Station

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CURRENCY_EURO,
    EntityCategory,
    UnitOfMass,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTRIBUTION,
    CONF_FUEL,
    CONF_MUNICIPALITY_ID,
    CONF_SHOW_ON_MAP,
    CONF_STATION_ID,
    CONFIGURATION_URL,
    DOMAIN,
    SUBENTRY_TYPE_STATION,
    SUBENTRY_TYPE_ZONE,
)
from .coordinator import (
    GeoportalGasolinerasConfigEntry,
    GeoportalGasolinerasCoordinator,
)
from .entity import StationEntity
from .names import brand_name

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


def price_unit(fuel: FuelType) -> str:
    """Return EUR per litre or per kilogram."""
    unit = UnitOfMass.KILOGRAMS if fuel in FUELS_PER_KG else UnitOfVolume.LITERS
    return f"{CURRENCY_EURO}/{unit}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoportalGasolinerasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the station and zone sensors."""
    coordinator = entry.runtime_data
    added: set[tuple[str, str]] = set()

    for zone in entry.get_subentries_of_type(SUBENTRY_TYPE_ZONE):
        async_add_entities(
            (
                ZoneSensor(coordinator, zone, key)
                for key in ("lowest_price", "average_price", "cheapest_station")
            ),
            config_subentry_id=zone.subentry_id,
        )

    @callback
    def async_add_station_sensors() -> None:
        """Add sensors for stations and fuels not seen before."""
        for subentry in entry.get_subentries_of_type(SUBENTRY_TYPE_STATION):
            station_id: str = subentry.data[CONF_STATION_ID]
            if (station := coordinator.data.stations.get(station_id)) is None:
                continue
            entities: list[SensorEntity] = []
            for fuel in station.prices:
                if (station_id, fuel) not in added:
                    added.add((station_id, fuel))
                    entities.append(FuelPriceSensor(coordinator, subentry, fuel))
            if (
                station_id in coordinator.data.updated_at
                and (station_id, "updated_at") not in added
            ):
                added.add((station_id, "updated_at"))
                entities.append(UpdatedAtSensor(coordinator, subentry, "updated_at"))
            if entities:
                async_add_entities(entities, config_subentry_id=subentry.subentry_id)

    async_add_station_sensors()
    entry.async_on_unload(coordinator.async_add_listener(async_add_station_sensors))


class FuelPriceSensor(StationEntity, SensorEntity):
    """Price of one fuel at a station."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3
    _unrecorded_attributes = frozenset({ATTR_LATITUDE, ATTR_LONGITUDE})

    def __init__(
        self,
        coordinator: GeoportalGasolinerasCoordinator,
        subentry: ConfigSubentry,
        fuel: FuelType,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, subentry, fuel.name.lower())
        self._fuel = fuel
        self._show_on_map: bool = subentry.data.get(CONF_SHOW_ON_MAP, False)
        self._attr_translation_key = fuel.name.lower()
        self._attr_native_unit_of_measurement = price_unit(fuel)

    @property
    @override
    def available(self) -> bool:
        """Return if the station still sells this fuel."""
        station = self.station
        return (
            super().available and station is not None and self._fuel in station.prices
        )

    @property
    @override
    def native_value(self) -> float:
        """Return the price; only called while available."""
        assert self.station is not None
        return self.station.prices[self._fuel]

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the location for the map, if enabled."""
        station = self.station
        if not self._show_on_map or station is None or station.latitude is None:
            return None
        return {ATTR_LATITUDE: station.latitude, ATTR_LONGITUDE: station.longitude}


class UpdatedAtSensor(StationEntity, SensorEntity):
    """When the Ministry published the prices."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "updated_at"

    @property
    @override
    def native_value(self) -> datetime | None:
        """Return the publication time."""
        return self.coordinator.data.updated_at.get(self._station_id)


class ZoneSensor(CoordinatorEntity[GeoportalGasolinerasCoordinator], SensorEntity):
    """Lowest price, average price or cheapest station of a fuel in a municipality."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GeoportalGasolinerasCoordinator,
        subentry: ConfigSubentry,
        key: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._municipality_id: str = subentry.data[CONF_MUNICIPALITY_ID]
        self._fuel = FuelType[subentry.data[CONF_FUEL].upper()]
        self._attr_translation_key = key
        self._attr_unique_id = f"zone_{subentry.unique_id}_{key}"
        if key != "cheapest_station":
            self._attr_native_unit_of_measurement = price_unit(self._fuel)
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 3
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"zone_{subentry.unique_id}")},
            name=subentry.title,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=CONFIGURATION_URL,
        )

    def _selling(self) -> list[Station]:
        """Return the stations of the municipality selling the fuel."""
        return [
            station
            for station in self.coordinator.data.municipalities.get(
                self._municipality_id, []
            )
            if self._fuel in station.prices
        ]

    @property
    @override
    def available(self) -> bool:
        """Return if some station sells the fuel."""
        return super().available and bool(self._selling())

    @property
    @override
    def native_value(self) -> float | str:
        """Return the value; only called while available."""
        selling = self._selling()
        prices = [station.prices[self._fuel] for station in selling]
        if self._key == "lowest_price":
            return min(prices)
        if self._key == "average_price":
            return round(mean(prices), 3)
        cheapest = min(selling, key=lambda station: station.prices[self._fuel])
        return f"{brand_name(cheapest.brand)} – {cheapest.address.title()}"

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the id and price of the cheapest station."""
        if self._key != "cheapest_station":
            return None
        cheapest = min(self._selling(), key=lambda station: station.prices[self._fuel])
        return {
            CONF_STATION_ID: cheapest.id,
            "price": cheapest.prices[self._fuel],
            "stations": len(self._selling()),
        }
