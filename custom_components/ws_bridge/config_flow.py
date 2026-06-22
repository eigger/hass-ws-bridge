"""Config flow: 범용 브릿지는 설정이 없다. 클라이언트가 HA URL+토큰으로 연결하므로
여기선 통합 인스턴스(단일)만 생성한다."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback

from .const import DOMAIN


class WsBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="WebSocket Bridge", data={})
        return self.async_show_form(step_id="user")

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types supported by this integration."""
        return {"gateway": GatewaySubentryFlowHandler}


class GatewaySubentryFlowHandler(ConfigSubentryFlow):
    """Add a gateway client as a subentry."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            gateway_id = user_input["gateway_id"].strip()
            name = user_input["name"].strip()

            # Check for duplicate subentries under this config entry
            for subentry in self._get_entry().subentries.values():
                if subentry.data.get("gateway_id") == gateway_id:
                    return self.async_abort(reason="already_configured")

            return self.async_create_entry(
                title=name,
                data={"gateway_id": gateway_id, "name": name},
                unique_id=gateway_id,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("gateway_id"): str,
                vol.Required("name"): str,
            }),
            errors=errors,
        )

