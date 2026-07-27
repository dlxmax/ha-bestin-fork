"""BESTIN 바이너리 센서 플랫폼 — Binary sensor platform for BESTIN.

도어락처럼 '잠김/해제' 만 노출되는 장치를 위한 플랫폼입니다.
v1.4.1 까지 도어락은 ``switch`` 로 노출되어 사용자가 토글을 시도해도 게이트웨이가
명령을 무시하는 (또는 검증되지 않은) 문제가 있었습니다. v1.4.2 부터 도어락은
``binary_sensor`` 로 등록되며 상태만 표시합니다.

Used for read-only state devices like doorlocks. Up through v1.4.1 the doorlock
was registered as a ``switch``, which let users toggle a UI control that the
gateway either ignored (iPark App / center) or handled with an unverified RS-485
packet (controller). v1.4.2 registers it as a ``binary_sensor`` so the UI shows
locked/unlocked state without offering a control surface that doesn't work.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import NEW_BINARY_SENSOR
from .device import BestinDevice
from .hub import BestinHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Set up the binary_sensor platform for BESTIN."""
    hub: BestinHub = BestinHub.get_hub(hass, entry)
    hub.entity_groups[BINARY_SENSOR_DOMAIN] = set()

    @callback
    def async_add_binary_sensor(devices: list | None = None) -> None:
        if devices is None:
            devices = hub.api.get_devices_from_domain(BINARY_SENSOR_DOMAIN)

        entities = [
            BestinBinarySensor(device, hub)
            for device in devices
            if device.unique_id not in hub.entity_groups[BINARY_SENSOR_DOMAIN]
        ]
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            hub.async_signal_new_device(NEW_BINARY_SENSOR),
            async_add_binary_sensor,
        )
    )
    async_add_binary_sensor()


class BestinBinarySensor(BestinDevice, BinarySensorEntity):
    """BESTIN 도어락 등 읽기 전용 상태 장치 — Read-only BESTIN device entity."""

    TYPE = BINARY_SENSOR_DOMAIN

    def __init__(self, device: Any, hub: BestinHub) -> None:
        super().__init__(device, hub)
        device_type = (device.info.device_type or "").split(":", 1)[0]
        # 도어락은 LOCK device_class 를 사용합니다 (HA 규약: True = 해제)
        # Doorlocks use the LOCK device class. HA convention: True = unlocked,
        # False = locked. Our wallpad reports ``True`` when unlocked, so the
        # mapping is direct.
        # 표시명("Door Lock" / "Away Mode")은 BestinDevice.__init__ 이
        # MAIN_DEVICES 유형에 대해 공통으로 붙여 줍니다 (v1.4.11).
        # Entity names ("Door Lock" / "Away Mode") come from
        # BestinDevice.__init__, which applies the friendly type label to all
        # MAIN_DEVICES types since v1.4.11.
        if device_type == "doorlock":
            # HA 규약: True = 해제, False = 잠김. 월패드도 해제 시 True 를
            # 보고하므로 그대로 매핑됩니다.
            # HA convention: True = unlocked, False = locked. Our wallpad
            # reports ``True`` when unlocked, so the mapping is direct.
            self._attr_device_class = BinarySensorDeviceClass.LOCK
        # 외출(away) 모드 — iparkapp 게이트웨이 전용. True = 외출(무장),
        # False = 재실(해제). 딱 맞는 device_class 가 없어 미설정 상태로 두면
        # HA 가 일반 on/off 바이너리 센서로 렌더링합니다.
        # Away mode is iparkapp-only. True = armed (unoccupied), False =
        # disarmed (normal). No HA device_class fits, so leaving it unset
        # renders a generic on/off binary sensor.

    @property
    def is_on(self) -> bool:
        """Return True when the underlying state is truthy."""
        state = self._device_info.state
        if isinstance(state, dict):
            # 일부 게이트웨이는 dict 로 상태를 보냅니다 — some gateways wrap state.
            return bool(state.get("state") or state.get("value") or state.get("is_on"))
        return bool(state)
