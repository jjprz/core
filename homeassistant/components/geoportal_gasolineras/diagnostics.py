"""Diagnostics support for Spain fuel prices (Geoportal Gasolineras)."""

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import GeoportalGasolinerasConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GeoportalGasolinerasConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (all public data)."""
    return {
        "entry": entry.as_dict(),
        "station": asdict(entry.runtime_data.data),
    }
