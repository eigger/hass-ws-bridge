"""Config flow: single instance plus options (allowed gateway token owners)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_ALLOWED_USER_IDS, DOMAIN


class WsBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="WebSocket Bridge", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WsBridgeOptionsFlow()


class WsBridgeOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_ALLOWED_USER_IDS: user_input.get(CONF_ALLOWED_USER_IDS, [])}
            )

        users = await self.hass.auth.async_get_users()
        choices = [
            {"value": u.id, "label": f"{u.name or u.id} ({u.id[:8]})"}
            for u in users
            if not u.system_generated and u.is_active
        ]
        valid = {c["value"] for c in choices}
        # 삭제·비활성된 사용자 ID는 선택지에 없으므로 기본값에서 제외한다.
        current = [
            uid
            for uid in self.config_entry.options.get(CONF_ALLOWED_USER_IDS, [])
            if uid in valid
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ALLOWED_USER_IDS, default=current
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=choices,
                            multiple=True,
                        )
                    ),
                }
            ),
        )
