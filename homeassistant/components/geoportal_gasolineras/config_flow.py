"""Config flow for Spain fuel prices (Geoportal Gasolineras)."""

import logging
from typing import Any, override

from aioprecioscarburantes import (
    FuelType,
    PreciosCarburantes,
    PreciosCarburantesError,
    PreciosCarburantesNotFoundError,
    Station,
)
import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME, UnitOfLength
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.util.location import distance

from .const import (
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
from .names import brand_name, municipality_name, station_name

_LOGGER = logging.getLogger(__name__)

DEFAULT_RADIUS = 10


def _selector(options: list[SelectOptionDict], *, sort: bool = True) -> SelectSelector:
    """Return a dropdown, sorted by label unless told otherwise."""
    if sort:
        options = sorted(options, key=lambda option: option["label"])
    return SelectSelector(
        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
    )


def _station_label(station: Station) -> str:
    return f"{brand_name(station.brand)} – {station.address.title()}"


class GeoportalGasolinerasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single config entry; stations and zones are subentries."""

    VERSION = 1

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types: fuel stations and zones."""
        return {
            SUBENTRY_TYPE_STATION: StationSubentryFlow,
            SUBENTRY_TYPE_ZONE: ZoneSubentryFlow,
        }

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Check the service can be reached and create the entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = PreciosCarburantes(session=async_get_clientsession(self.hass))
            try:
                await client.get_provinces()
            except PreciosCarburantesError:
                _LOGGER.debug("Cannot reach the service", exc_info=True)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="Spain fuel prices", data={})
        return self.async_show_form(step_id="user", errors=errors)


class _LocationSubentryFlow(ConfigSubentryFlow):
    """Shared province and municipality steps."""

    def __init__(self) -> None:
        """Initialize the flow."""
        self._province_id = ""
        self._municipality_id = ""
        self._municipality_name = ""

    @property
    def _client(self) -> PreciosCarburantes:
        return PreciosCarburantes(session=async_get_clientsession(self.hass))

    async def _async_after_municipality(self) -> SubentryFlowResult:
        """Continue once the municipality is chosen."""
        raise NotImplementedError

    async def _async_province_options(self) -> list[SelectOptionDict] | None:
        """Return the provinces, or None if they cannot be fetched."""
        try:
            provinces = await self._client.get_provinces()
        except PreciosCarburantesError:
            _LOGGER.debug("Cannot get provinces", exc_info=True)
            return None
        return [
            SelectOptionDict(value=province.id, label=province.name.title())
            for province in provinces
        ]

    async def async_step_province(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Choose the province."""
        if user_input is not None:
            self._province_id = user_input[CONF_PROVINCE_ID]
            return await self.async_step_municipality()
        if (options := await self._async_province_options()) is None:
            return self.async_abort(reason="cannot_connect")
        return self.async_show_form(
            step_id="province",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_PROVINCE_ID): _selector(options)}
            ),
        )

    async def async_step_municipality(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Choose the municipality."""
        try:
            municipalities = await self._client.get_municipalities(self._province_id)
        except PreciosCarburantesError:
            _LOGGER.debug("Cannot get municipalities", exc_info=True)
            return self.async_abort(reason="cannot_connect")
        names = {municipality.id: municipality.name for municipality in municipalities}
        if user_input is not None:
            self._municipality_id = user_input[CONF_MUNICIPALITY_ID]
            self._municipality_name = names.get(self._municipality_id, "")
            return await self._async_after_municipality()
        return self.async_show_form(
            step_id="municipality",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_MUNICIPALITY_ID): _selector(
                        [
                            SelectOptionDict(value=key, label=name)
                            for key, name in names.items()
                        ]
                    )
                }
            ),
        )


class StationSubentryFlow(_LocationSubentryFlow):
    """Add a fuel station from a list, near home or by its code."""

    def __init__(self) -> None:
        """Initialize the flow."""
        super().__init__()
        self._stations: dict[str, Station] = {}
        self._labels: dict[str, str] = {}

    def _is_configured(self, station_id: str) -> bool:
        """Return if the station was already added."""
        return any(
            subentry.unique_id == station_id
            for subentry in self._get_entry().get_subentries_of_type(
                SUBENTRY_TYPE_STATION
            )
        )

    def _create(self, station: Station, data: dict[str, Any]) -> SubentryFlowResult:
        """Create the station subentry with a unique readable name."""
        taken = {subentry.title for subentry in self._get_entry().subentries.values()}
        return self.async_create_entry(
            title=station_name(station, taken),
            data={**data, CONF_STATION_ID: station.id, CONF_SHOW_ON_MAP: False},
            unique_id=station.id,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Choose how to find the station."""
        return self.async_show_menu(
            step_id="user", menu_options=["province", "nearby", "station_code"]
        )

    async def async_step_station_code(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a station by its code, also one with restricted sales."""
        errors: dict[str, str] = {}
        if user_input is not None:
            station_id = user_input[CONF_STATION_ID].strip()
            if self._is_configured(station_id):
                return self.async_abort(reason="already_configured")
            try:
                station = await self._client.get_station_by_id(station_id)
            except PreciosCarburantesNotFoundError:
                errors["base"] = "station_not_found"
            except PreciosCarburantesError:
                _LOGGER.debug("Cannot get station %s", station_id, exc_info=True)
                errors["base"] = "cannot_connect"
            else:
                return self._create(station, {})
        return self.async_show_form(
            step_id="station_code",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_STATION_ID): TextSelector()}
            ),
            errors=errors,
        )

    async def async_step_nearby(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """List the stations of a province within a distance of home."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._province_id = user_input[CONF_PROVINCE_ID]
            radius = user_input[CONF_RADIUS] * 1000
            try:
                result = await self._client.get_stations_by_province(self._province_id)
            except PreciosCarburantesError:
                _LOGGER.debug("Cannot get stations", exc_info=True)
                errors["base"] = "cannot_connect"
            else:
                home = (self.hass.config.latitude, self.hass.config.longitude)
                nearby: list[tuple[float, Station]] = []
                for station in result.stations:
                    if station.latitude is None or station.longitude is None:
                        continue
                    meters = distance(*home, station.latitude, station.longitude)
                    if (
                        meters is not None
                        and meters <= radius
                        and not self._is_configured(station.id)
                    ):
                        nearby.append((meters, station))
                nearby.sort(key=lambda item: item[0])
                self._stations = {station.id: station for _, station in nearby}
                self._labels = {
                    station.id: (
                        f"{_station_label(station)}, "
                        f"{municipality_name(station.municipality)} "
                        f"({meters / 1000:.1f} km)"
                    )
                    for meters, station in nearby
                }
                if self._stations:
                    return await self.async_step_station()
                errors["base"] = "no_stations_nearby"
        if (options := await self._async_province_options()) is None:
            return self.async_abort(reason="cannot_connect")
        return self.async_show_form(
            step_id="nearby",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_PROVINCE_ID): _selector(options),
                    probatio.Required(
                        CONF_RADIUS, default=DEFAULT_RADIUS
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=100,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement=UnitOfLength.KILOMETERS,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @override
    async def _async_after_municipality(self) -> SubentryFlowResult:
        """List the stations of the municipality."""
        try:
            result = await self._client.get_stations_by_municipality(
                self._municipality_id
            )
        except PreciosCarburantesError:
            _LOGGER.debug("Cannot get stations", exc_info=True)
            return self.async_abort(reason="cannot_connect")
        self._stations = {
            station.id: station
            for station in result.stations
            if not self._is_configured(station.id)
        }
        if not self._stations:
            return self.async_abort(reason="no_stations")
        self._labels = {
            station.id: _station_label(station) for station in self._stations.values()
        }
        return await self.async_step_station()

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Choose the station."""
        if user_input is not None:
            station = self._stations[user_input[CONF_STATION_ID]]
            return self._create(
                station,
                {
                    CONF_PROVINCE_ID: station.province_id,
                    CONF_MUNICIPALITY_ID: station.municipality_id,
                },
            )
        return self.async_show_form(
            step_id="station",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_STATION_ID): _selector(
                        [
                            SelectOptionDict(value=key, label=label)
                            for key, label in self._labels.items()
                        ],
                        sort=False,
                    )
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Rename the station and choose whether it is shown on the map."""
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=user_input[CONF_NAME].strip() or subentry.title,
                data={**subentry.data, CONF_SHOW_ON_MAP: user_input[CONF_SHOW_ON_MAP]},
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_NAME, default=subentry.title
                    ): TextSelector(),
                    probatio.Required(
                        CONF_SHOW_ON_MAP,
                        default=subentry.data.get(CONF_SHOW_ON_MAP, False),
                    ): BooleanSelector(),
                }
            ),
        )


class ZoneSubentryFlow(_LocationSubentryFlow):
    """Follow the lowest and average price of a fuel in a municipality."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Start with the province."""
        return await self.async_step_province()

    @override
    async def _async_after_municipality(self) -> SubentryFlowResult:
        return await self.async_step_fuel()

    async def async_step_fuel(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Choose the fuel."""
        if user_input is not None:
            fuel = FuelType[user_input[CONF_FUEL].upper()]
            unique_id = f"{self._municipality_id}_{fuel.name.lower()}"
            if any(
                subentry.unique_id == unique_id
                for subentry in self._get_entry().subentries.values()
            ):
                return self.async_abort(reason="already_configured")
            return self.async_create_entry(
                title=f"{fuel.value} – {municipality_name(self._municipality_name)}",
                data={
                    CONF_PROVINCE_ID: self._province_id,
                    CONF_MUNICIPALITY_ID: self._municipality_id,
                    CONF_FUEL: fuel.name.lower(),
                },
                unique_id=unique_id,
            )
        return self.async_show_form(
            step_id="fuel",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_FUEL): SelectSelector(
                        SelectSelectorConfig(
                            options=[fuel.name.lower() for fuel in FuelType],
                            translation_key="fuel",
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )
