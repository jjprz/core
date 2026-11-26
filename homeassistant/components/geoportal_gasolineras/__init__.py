"""The Spain fuel prices (Geoportal Gasolineras) integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import (
    GeoportalGasolinerasConfigEntry,
    GeoportalGasolinerasCoordinator,
    removed_issue_id,
)
from .services import async_setup_services

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: GeoportalGasolinerasConfigEntry
) -> None:
    """Set up the fuel stations and zones of the config entry."""
    _async_remove_stale_issues(hass, entry)
    coordinator = GeoportalGasolinerasCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


def _async_remove_stale_issues(
    hass: HomeAssistant, entry: GeoportalGasolinerasConfigEntry
) -> None:
    """Delete the issues of stations that were removed."""
    current = {removed_issue_id(subentry) for subentry in entry.subentries.values()}
    for domain, issue_id in list(ir.async_get(hass).issues):
        if (
            domain == DOMAIN
            and issue_id.startswith("station_removed_")
            and issue_id not in current
        ):
            ir.async_delete_issue(hass, DOMAIN, issue_id)


async def _async_update_listener(
    hass: HomeAssistant, entry: GeoportalGasolinerasConfigEntry
) -> None:
    """Reload when a station or zone is added, changed or removed."""
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: GeoportalGasolinerasConfigEntry
) -> None:
    """Unload a config entry."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
