"""Base class for BESTIN devices."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import Entity, DeviceInfo
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
        """
        if (device_type := self._device_info.device_type) not in MAIN_DEVICES:
            stable_id = formatted_name(device_type)
            display_label = _friendly_type_label(device_type)
            device_name = f"{self.hub.name} {display_label}"
        else:
            stable_id = self.hub.model
            device_name = self.hub.name

        return DeviceInfo(
            connections={(self.hub.hub_id, self.unique_id)},
            identifiers={(DOMAIN, f"{self.hub.wp_version}_{stable_id}")},
            manufacturer="HDC Labs Co., Ltd.",
            model=self.hub.wp_version,
            name=device_name,
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
        """Cleanup when the entity is removed from HASS."""
        self._device.remove_callback(self.async_update_callback)
        del self.hub.entity_to_id[self.entity_id]
        self.hub.entity_groups[self.TYPE].remove(self.unique_id)

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
        """Get additional state attributes."""
        attributes = {
            "unique_id": self.unique_id,
            "device_room": self._device_info.room,
            "device_type": self._device_info.device_type,
        }
        if self.should_poll and not "elevator" in self.entity_id:
            attributes["last_update_time"] = self.hub.api.last_update_time
            attributes["last_sess_refresh"] = self.hub.api.last_sess_refresh
        
        return attributes
