"""Fan platform for BESTIN"""

from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.fan import (
    DOMAIN as FAN_DOMAIN,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    FanEntity,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_OFF, ATTR_STATE, WIND_SPEED
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import (
    CONF_VERSION,
    SPEED_STR_LOW,
    NEW_FAN,
    PRESET_NV,
)
from .device import BestinDevice
from .hub import BestinHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Setup fan platform."""
    hub: BestinHub = BestinHub.get_hub(hass, entry)
    hub.entity_groups[FAN_DOMAIN] = set()

    @callback
    def async_add_fan(devices=None):
        if devices is None:
            devices = hub.api.get_devices_from_domain(FAN_DOMAIN)

        entities = [
            BestinFan(device, hub) 
            for device in devices 
            if device.unique_id not in hub.entity_groups[FAN_DOMAIN]
        ]

        if entities:
            async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, hub.async_signal_new_device(NEW_FAN), async_add_fan
        )
    )
    async_add_fan()


class BestinFan(BestinDevice, FanEntity):
    """Defined the Fan."""
    TYPE = FAN_DOMAIN

    def __init__(self, device, hub) -> None:
        """Initialize the fan."""
        super().__init__(device, hub)
        # iparkapp 의 ventil 은 초기 상태가 bool ("on"/"off") 이고, center /
        # controller 는 dict (speed_list, preset_modes 등) 를 보냅니다. v1.4.4
        # 까지는 항상 dict 를 가정해 ``state.get(...)`` 가 bool 위에서 즉시
        # AttributeError 로 깨졌고, 결과적으로 모든 iparkapp 사용자의 fan 플랫폼
        # 등록이 통째로 실패했습니다 (다른 게이트웨이의 fan/ventil 은 영향 없음).
        # The ventil entity arrives as either a bool (iparkapp — just on/off)
        # or a dict (center / controller — with speed_list / preset_modes).
        # Up to v1.4.4 the unconditional ``state.get(...)`` raised
        # AttributeError on the bool form and broke the entire fan platform
        # for every iparkapp user. Be defensive and degrade gracefully.
        self._version_exists = getattr(hub.api, CONF_VERSION, False)

        self._supported_features = (
            FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        )
        state = self._device_info.state
        if isinstance(state, dict):
            self._speed_list = state.get("speed_list")
            self._preset_modes = state.get(ATTR_PRESET_MODES)
            if self._speed_list:
                self._supported_features |= FanEntityFeature.SET_SPEED
            if self._preset_modes:
                self._supported_features |= FanEntityFeature.PRESET_MODE
        else:
            # iparkapp: simple on/off ventil, no speed levels / presets.
            self._speed_list = None
            self._preset_modes = None

    @property
    def is_on(self) -> bool:
        """Return true if fan is on."""
        state = self._device_info.state
        if isinstance(state, dict):
            return state[ATTR_STATE]
        return bool(state)

    @property
    def supported_features(self) -> FanEntityFeature:
        """Flag supported features."""
        return self._supported_features

    @property
    def percentage(self) -> Optional[int]:
        """Return the current speed percentage."""
        if not self._speed_list:
            # iparkapp ventil — no speed control, surface on/off as 0/100.
            return 100 if self.is_on else 0
        speed = self._device_info.state[WIND_SPEED]
        if speed == STATE_OFF:
            return 0
        return ordered_list_item_to_percentage(self._speed_list, speed)

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return len(self._speed_list) if self._speed_list else 1

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        if percentage == 0:
            await self.enqueue_command(STATE_OFF if self._version_exists else False)
        else:
            percentage = percentage_to_ordered_list_item(self._speed_list, percentage)
            if percentage == SPEED_STR_LOW and self.is_on is False:
                await self.enqueue_command(STATE_ON)
            else:
                await self.enqueue_command(set_percentage=percentage)

    @property
    def preset_mode(self) -> str:
        """Return the preset mode."""
        return self._device_info.state[ATTR_PRESET_MODE]

    @property
    def preset_modes(self) -> list:
        """Return the list of available preset modes."""
        return self._preset_modes

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        await self.enqueue_command(preset_mode=preset_mode == PRESET_NV)

    async def async_turn_on(
        self,
        speed: Optional[str] = None,
        percentage: Optional[int] = None,
        preset_mode: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Turn on fan."""
        await self.enqueue_command(STATE_ON if self._version_exists else True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off fan."""
        await self.enqueue_command(STATE_OFF if self._version_exists else False)
