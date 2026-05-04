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

from .const import FRIENDLY_TYPE_NAMES, NEW_BINARY_SENSOR
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
        if device_type == "doorlock":
            self._attr_device_class = BinarySensorDeviceClass.LOCK
            # 도어락은 MAIN_DEVICES 에 속해 hub 디바이스 아래로 묶입니다.
            # 그래서 device_info.name 에는 친근한 라벨이 붙지 않으므로,
            # entity_name 에 "Door Lock" 를 명시해 'BESTIN Door Lock' 형태로
            # 보이게 합니다.
            # Doorlocks live under the hub device (because they're in
            # MAIN_DEVICES), so device_info.name does not carry a friendly
            # label. We set the entity name to "Door Lock" so HA composes
            # "BESTIN Door Lock" as the final friendly_name.
            self._attr_name = FRIENDLY_TYPE_NAMES.get("doorlock", "Door Lock")
        elif device_type == "mode":
            # 외출(away) 모드 — iparkapp 게이트웨이에서만 노출됨.  alarm 시스템
            # 의 무장 상태를 표시. True = 외출(무장), False = 재실(해제).
            # iparkapp away/alarm-arm state. True = armed (unoccupied),
            # False = disarmed (normal). No HA device_class fits perfectly;
            # leave unset so HA renders a generic on/off binary sensor.
            self._attr_name = FRIENDLY_TYPE_NAMES.get("mode", "Away Mode")

    @property
    def is_on(self) -> bool:
        """Return True when the underlying state is truthy."""
        state = self._device_info.state
        if isinstance(state, dict):
            # 일부 게이트웨이는 dict 로 상태를 보냅니다 — some gateways wrap state.
            return bool(state.get("state") or state.get("value") or state.get("is_on"))
        return bool(state)
