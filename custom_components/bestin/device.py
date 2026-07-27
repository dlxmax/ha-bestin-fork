"""Base class for BESTIN devices."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.core import callback

from .const import DOMAIN, FRIENDLY_TYPE_NAMES, MAIN_DEVICES
from .until import formatted_name


def _friendly_type_label(device_type: str) -> str:
    """친근한 표시명을 반환합니다 — Return the user-facing label for ``device_type``.

    Falls back to title-casing the raw type when no friendly mapping exists.
    Sub-typed values like ``outlet:cutvalue`` strip the colon-suffix first,
    so ``outlet:cutvalue`` resolves via the ``outlet`` entry.
    """
    base = device_type.split(":", 1)[0] if ":" in device_type else device_type
    return FRIENDLY_TYPE_NAMES.get(base, formatted_name(base))


class BestinBase:
    """Base class for BESTIN devices."""

    def __init__(self, device, hub):
        """Initialize device and hub."""
        self._device = device
        self._device_info = device.info
        self.hub = hub

    async def enqueue_command(self, data: Any = None, **kwargs):
        """Send commands to the device."""
        await self._device.enqueue_command(self._device_info.device_id, data, **kwargs)

    @property
    def unique_id(self) -> str:
        """Get unique device ID."""
        return self._device.unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Get device registry information.

        ``identifiers`` keep the raw, version-stable type string so that an
        upgrade does not orphan existing devices in the registry. ``name`` uses
        the friendly label so the UI shows e.g. "BESTIN Light" instead of the
        internal "BESTIN Livinglight".

        MAIN_DEVICES (도어락 / 외출 모드 / 환기 등 세대에 하나뿐인 장치) 는
        허브 디바이스 자체에 붙습니다. v1.4.10 까지는 별도의 "BESTIN" 디바이스를
        하나 더 만들었기 때문에, 통합 페이지에 이름이 같은 디바이스가 둘
        보였습니다 — 하나는 엔티티가 하나도 없이 자식 디바이스 링크만 나열하는
        빈 껍데기였습니다. v1.4.11 부터는 하나로 합칩니다.

        MAIN_DEVICES (doorlock / away mode / ventilation — the one-per-home
        devices) attach to the hub device itself. Up to v1.4.10 they got their
        own registry entry that shared the hub's name, so the integration page
        listed two devices called "BESTIN": the hub, holding no entities at all
        and rendering as nothing but a list of links to its children, and the
        real one. v1.4.11 collapses them into a single device.
        """
        if (device_type := self._device_info.device_type) in MAIN_DEVICES:
            return DeviceInfo(
                identifiers={(DOMAIN, str(self.hub.hub_id))},
                manufacturer="HDC Labs Co., Ltd.",
                model=self.hub.wp_version,
                name=self.hub.name,
                sw_version=self.hub.sw_version,
            )

        stable_id = formatted_name(device_type)
        display_label = _friendly_type_label(device_type)
        return DeviceInfo(
            connections={(self.hub.hub_id, self.unique_id)},
            identifiers={(DOMAIN, f"{self.hub.wp_version}_{stable_id}")},
            manufacturer="HDC Labs Co., Ltd.",
            model=self.hub.wp_version,
            name=f"{self.hub.name} {display_label}",
            sw_version=self.hub.sw_version,
            via_device=(DOMAIN, str(self.hub.hub_id)),
        )


class BestinDevice(BestinBase, Entity):
    """Define the Bestin Device entity."""

    TYPE = ""

    def __init__(self, device, hub):
        """Initialize device and update callbacks."""
        super().__init__(device, hub)
        self.hub.entity_groups[self.TYPE].add(self.unique_id)
        self._attr_has_entity_name = True
        # 세대에 하나뿐인 장치(도어락 / 외출 모드 / 환기 / 가스)는 허브
        # 디바이스에 직접 붙으므로, 디바이스 이름이 유형을 알려주지 못합니다.
        # 게이트웨이가 만들어 준 이름은 이런 장치의 경우 방 번호("1") 뿐이라
        # UI 에 "BESTIN 1" 처럼 표시됐습니다. 유형 라벨을 대신 씁니다.
        # 'elevator:direction' 같은 콜론 하위 유형은 같은 라벨로 겹치므로
        # 원래 이름을 유지합니다.
        #
        # One-per-home devices (doorlock / away mode / ventilation / gas)
        # attach directly to the hub device, so the device name carries no
        # type information. The gateways name these after their room number
        # ("1"), which rendered as "BESTIN 1" in the UI. Use the friendly type
        # label instead. Colon sub-types like 'elevator:direction' would all
        # collapse to the same label, so they keep their original name.
        device_type = self._device_info.device_type
        if device_type in MAIN_DEVICES and ":" not in device_type:
            self._attr_name = _friendly_type_label(device_type)
        else:
            self._attr_name = self._device_info.name

    @property
    def entity_registry_enabled_default(self):
        """Check if the entity is enabled by default."""
        return True

    async def async_added_to_hass(self):
        """Subscribe to device events upon addition to HASS."""
        self._device.add_callback(self.async_update_callback)
        self.hub.entity_to_id[self.entity_id] = self._device_info.device_id
        self.schedule_update_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Cleanup when the entity is removed from HASS.

        ``discard``/``pop`` 를 쓰는 이유: 엔티티가 등록되기 전에 제거되거나
        (설정 중 오류) 같은 엔티티가 두 번 정리되면 ``del`` / ``set.remove``
        가 KeyError 를 던져 HA 의 언로드 절차 전체가 중단됩니다.

        Tolerate a missing key: if an entity is removed before it finished
        registering, or cleaned up twice, ``del``/``set.remove`` would raise
        KeyError and abort HA's whole unload sequence — leaving the rest of
        the integration half-torn-down.
        """
        self._device.remove_callback(self.async_update_callback)
        self.hub.entity_to_id.pop(self.entity_id, None)
        self.hub.entity_groups[self.TYPE].discard(self.unique_id)

    @callback
    def async_restore_last_state(self, last_state) -> None:
        """Restore the last known state (not implemented)."""
        pass

    @callback
    def async_update_callback(self):
        """Trigger an update of the device state."""
        self.async_schedule_update_ha_state()

    @property
    def available(self) -> bool:
        """Check if the device is available."""
        return self.hub.available

    @property
    def should_poll(self) -> bool:
        """Determine if the device requires polling."""
        return self.hub.is_polling

    @property
    def extra_state_attributes(self) -> dict:
        """Get additional state attributes.

        여기 들어가는 값은 모두 '엔티티가 실제로 변할 때만 변하는' 것이어야
        합니다. HA 는 state 와 attributes 가 이전과 완전히 같으면 recorder 에
        아무 것도 쓰지 않고 넘어가는데 (core.async_set_internal 의
        ``same_state and same_attr`` 분기), 매 폴링마다 값이 바뀌는 속성이
        하나라도 있으면 그 최적화가 통째로 무력화됩니다.

        v1.4.11 까지 이 자리에는 ``last_update_time`` / ``last_sess_refresh``
        가 있었습니다. 둘 다 허브 단위 진단값이라 24개 엔티티에 똑같이
        복제되었고, 30초 폴링마다 값이 바뀌었습니다. 그 결과 며칠째 값이
        그대로인 센서까지 하루 약 2,800행씩 기록했습니다 — 실측:
        ``sensor.bestin_energy_neighbor_avg_gas`` 는 24시간에 2,778행을
        남겼지만 서로 다른 값은 3개뿐이었습니다.

        Everything here must change only when the entity itself changes. HA
        skips the recorder entirely when state and attributes both match the
        previous write (the ``same_state and same_attr`` branch in
        ``core.async_set_internal``) — but a single attribute that ticks on
        every poll defeats that optimisation for the whole entity.

        Through v1.4.11 this returned ``last_update_time`` /
        ``last_sess_refresh``. Both are hub-wide diagnostics, identical across
        all 24 entities, and both changed on every 30 s poll — so every entity
        wrote a new row every poll even when nothing about it had changed.
        Measured on a live install: ``sensor.bestin_energy_neighbor_avg_gas``
        logged 2,778 rows in 24 h across just 3 distinct values, and the
        integration as a whole wrote ~67,000 rows/day that were almost
        entirely duplicates. Polling timestamps belong on one hub-level
        diagnostic entity, not stamped onto every entity's state.
        """
        return {
            "unique_id": self.unique_id,
            "device_room": self._device_info.room,
            "device_type": self._device_info.device_type,
        }
