"""The BESTIN component."""

from __future__ import annotations

import asyncio
import re

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN, LOGGER, PLATFORMS, CONF_SESSION
from .hub import BestinHub
from .iparkapp_const import CONF_IPARKAPP_SITE


def _cleanup_legacy_doorlock_switches(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """v1.4.2 마이그레이션: 도어락이 switch → binary_sensor 로 이동했습니다.

    HA 1.4.1 이하에서 도어락은 ``switch`` 도메인에 등록되었지만 게이트웨이는
    제어를 지원하지 않았습니다. 1.4.2 부터는 ``binary_sensor`` 로 등록되므로,
    오래된 ``switch.*doorlock*`` 엔트리가 'unavailable' 로 남아 보이지 않도록
    엔티티 레지스트리에서 제거합니다.

    v1.4.2 migration: doorlock moved from ``switch`` (which the gateway did not
    actually control) to ``binary_sensor`` (read-only state). Any existing
    switch entries with ``unique_id`` containing ``doorlock`` are removed from
    the entity registry so they do not linger as 'unavailable' orphans.
    """
    registry = er.async_get(hass)
    removed = 0
    for entity_id, ent in list(registry.entities.items()):
        if ent.config_entry_id != entry.entry_id:
            continue
        if ent.domain != Platform.SWITCH.value:
            continue
        if "doorlock" not in (ent.unique_id or "").lower():
            continue
        registry.async_remove(entity_id)
        removed += 1
    if removed:
        LOGGER.info(
            "v1.4.2 마이그레이션: 오래된 도어락 switch 엔티티 %d개 제거 / "
            "Removed %d legacy doorlock switch entries.",
            removed,
            removed,
        )


# urlsafe-base64 hash suffix may include '_' and '-' (e.g. 'RI4_NLDU').
_LEGACY_HEATSOURCE_RE = re.compile(r"^bestin_heatsource_\d+_supply(-[A-Z0-9_-]+)?$")


def _cleanup_legacy_heatsource_sensors(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """v1.4.3 마이그레이션: heatsource 센서가 BESTIN Energy 로 이동했습니다.

    1.4.2 까지 ``BESTIN Heat Sensor`` 디바이스 그룹에 노출되던
    ``bestin_heatsource_<n>_supply-<hash>`` 엔티티는 1.4.3 부터 BESTIN Energy
    그룹의 ``bestin_energy_1_heat_supply*`` 로 이동했습니다. 자동 rename 대신
    레지스트리에서 제거하고, 다음 폴링에서 새 unique_id 로 다시 등록되도록
    합니다 (v1.4.2 의 도어락 정리와 동일한 트레이드오프).

    v1.4.3 migration: the orphan "BESTIN Heat Sensor" device group was folded
    into BESTIN Energy as "Heating supply". Drop the legacy
    ``bestin_heatsource_<n>_supply-*`` entries; new
    ``bestin_energy_1_heat_supply*`` entities appear on the next poll. Same
    trade-off the v1.4.2 doorlock cleanup made.
    """
    registry = er.async_get(hass)
    removed = 0
    for entity_id, ent in list(registry.entities.items()):
        if ent.config_entry_id != entry.entry_id:
            continue
        if not _LEGACY_HEATSOURCE_RE.match(ent.unique_id or ""):
            continue
        registry.async_remove(entity_id)
        removed += 1
    if removed:
        LOGGER.info(
            "v1.4.3 마이그레이션: 오래된 heatsource 센서 %d개 제거 / "
            "Removed %d legacy heatsource sensor entries (folded into BESTIN Energy).",
            removed,
            removed,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the BESTIN integration."""
    _cleanup_legacy_doorlock_switches(hass, entry)
    _cleanup_legacy_heatsource_sensors(hass, entry)
    hub = BestinHub(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    # 허브 디바이스 등록 — Register the hub as a device so per-platform
    # device entries' ``via_device`` references resolve. v1.4.3 까지는 각 엔티티
    # 가 ``via_device=(DOMAIN, hub_id)`` 를 선언했지만 일치하는 부모 디바이스
    # 가 등록되지 않아 HA 가 경고를 찍었고, HA 2025.12 부터는 이로 인해 엔티티
    # 가 unavailable 로 빠집니다. 모든 게이트웨이 (controller, center, iparkapp)
    # 에 공통으로 적용됩니다. v1.4.4.
    # Without this, HA logs:
    #   'device_registry.async_get_or_create' referencing a non existing
    #   `via_device` (...). This will stop working in Home Assistant 2025.12.0.
    # ...and on HA ≥ 2025.12 it actually breaks: every entity with a missing
    # via_device parent is rendered "unavailable".
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, str(hub.hub_id))},
        manufacturer="HDC Labs Co., Ltd.",
        model=hub.wp_version,
        name=hub.name,
        sw_version=hub.sw_version,
    )

    # iPark 스마트홈 앱 — new gateway type takes precedence when its key is present.
    if CONF_IPARKAPP_SITE in entry.data:
        LOGGER.info("Start iParkApp initialization.")
        await hub.async_initialize_iparkapp()
    elif CONF_SESSION not in entry.data:
        try:
            await asyncio.wait_for(hub.connect(), timeout=5)
        except asyncio.TimeoutError as ex:
            await hub.async_close()
            hass.data[DOMAIN].pop(entry.entry_id)
            raise ConfigEntryNotReady(f"Connection to {hub.hub_id} timed out.") from ex

        LOGGER.info("Start serial initialization.")
        await hub.async_initialize_serial()
    else:
        LOGGER.info("Start center initialization.")
        await hub.async_initialize_center()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, hub.shutdown)
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the BESTIN integration."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        hub: BestinHub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.async_close()

    return unload_ok
