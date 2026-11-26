"""Repairs for Spain fuel prices (Geoportal Gasolineras)."""

import probatio

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant


class RemoveStationRepairFlow(RepairsFlow):
    """Delete a fuel station that is no longer listed."""

    def __init__(self, entry_id: str, subentry_id: str) -> None:
        """Initialize the flow."""
        self._entry_id = entry_id
        self._subentry_id = subentry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Ask to delete the station."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Delete the station once confirmed."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or self._subentry_id not in entry.subentries:
            return self.async_abort(reason="station_already_removed")
        if user_input is not None:
            self.hass.config_entries.async_remove_subentry(entry, self._subentry_id)
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm",
            data_schema=probatio.Schema({}),
            description_placeholders={
                "name": entry.subentries[self._subentry_id].title
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow of a removed station."""
    assert data is not None
    return RemoveStationRepairFlow(str(data["entry_id"]), str(data["subentry_id"]))
