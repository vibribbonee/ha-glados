"""Config flow for GLaDOS."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class GladosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up GLaDOS. There is one per Home Assistant."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry; settings arrive with the next phases."""
        if user_input is not None:
            return self.async_create_entry(title="GLaDOS", data={})
        return self.async_show_form(step_id="user")
