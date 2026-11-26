"""Config flow for Spain fuel prices (Geoportal Gasolineras)."""

import logging
from typing import Any, override

from aioprecioscarburantes import (
    PreciosCarburantes,
    PreciosCarburantesError,
    PreciosCarburantesNotFoundError,
    Station,
)
import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import CONF_MUNICIPALITY_ID, CONF_PROVINCE_ID, CONF_STATION_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _selector(options: list[SelectOptionDict]) -> SelectSelector:
    """Return a dropdown sorted by label."""
    return SelectSelector(
        SelectSelectorConfig(
            options=sorted(options, key=lambda option: option["label"]),
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def station_title(station: Station) -> str:
    """Return a readable name for a station."""
    return f"{station.brand.title()} {station.locality.title()}"


class GeoportalGasolinerasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Choose a province, a municipality and a fuel station."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._province_id = ""
        self._municipality_id = ""
        self._stations: dict[str, Station] = {}

    @property
    def _client(self) -> PreciosCarburantes:
        return PreciosCarburantes(session=async_get_clientsession(self.hass))

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how to find the station."""
        return self.async_show_menu(
            step_id="user", menu_options=["province", "station_code"]
        )

    async def async_step_station_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a station by its code, also one with restricted sales."""
        errors: dict[str, str] = {}
        if user_input is not None:
            station_id = user_input[CONF_STATION_ID].strip()
            try:
                station = await self._client.get_station_by_id(station_id)
            except PreciosCarburantesNotFoundError:
                errors["base"] = "station_not_found"
            except PreciosCarburantesError:
                _LOGGER.debug("Cannot get station %s", station_id, exc_info=True)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(station.id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=station_title(station),
                    data={CONF_STATION_ID: station.id},
                )
        return self.async_show_form(
            step_id="station_code",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_STATION_ID): TextSelector()}
            ),
            errors=errors,
        )

    async def async_step_province(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the province."""
        if user_input is not None:
            self._province_id = user_input[CONF_PROVINCE_ID]
            return await self.async_step_municipality()
        try:
            provinces = await self._client.get_provinces()
        except PreciosCarburantesError:
            _LOGGER.debug("Cannot get provinces", exc_info=True)
            return self.async_abort(reason="cannot_connect")
        options = [
            SelectOptionDict(value=province.id, label=province.name.title())
            for province in provinces
        ]
        return self.async_show_form(
            step_id="province",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_PROVINCE_ID): _selector(options)}
            ),
        )

    async def async_step_municipality(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the municipality."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._municipality_id = user_input[CONF_MUNICIPALITY_ID]
            try:
                result = await self._client.get_stations_by_municipality(
                    self._municipality_id
                )
            except PreciosCarburantesError:
                _LOGGER.debug("Cannot get stations", exc_info=True)
                errors["base"] = "cannot_connect"
            else:
                self._stations = {station.id: station for station in result.stations}
                if self._stations:
                    return await self.async_step_station()
                errors["base"] = "no_stations"
        try:
            municipalities = await self._client.get_municipalities(self._province_id)
        except PreciosCarburantesError:
            _LOGGER.debug("Cannot get municipalities", exc_info=True)
            return self.async_abort(reason="cannot_connect")
        options = [
            SelectOptionDict(value=municipality.id, label=municipality.name)
            for municipality in municipalities
        ]
        return self.async_show_form(
            step_id="municipality",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_MUNICIPALITY_ID): _selector(options)}
            ),
            errors=errors,
        )

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the station."""
        if user_input is not None:
            station = self._stations[user_input[CONF_STATION_ID]]
            await self.async_set_unique_id(station.id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=station_title(station),
                data={
                    CONF_PROVINCE_ID: self._province_id,
                    CONF_MUNICIPALITY_ID: self._municipality_id,
                    CONF_STATION_ID: station.id,
                },
            )
        options = [
            SelectOptionDict(
                value=station.id,
                label=f"{station.brand.title()} – {station.address.title()}",
            )
            for station in self._stations.values()
        ]
        return self.async_show_form(
            step_id="station",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_STATION_ID): _selector(options)}
            ),
        )
