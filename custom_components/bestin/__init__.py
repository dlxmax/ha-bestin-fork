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
_HASH_SUFFIX = r"(-[A-Z0-9_-]+)?"
_LEGACY_HEATSOURCE_RE = re.compile(rf"^bestin_heatsource_\d+_supply{_HASH_SUFFIX}$")

# v1.4.11 — 도어락 unique_id 가 서버 응답의 unit_num 철자에 딸려 다녔습니다.
# ``bestin_doorlock_<n>_doorlock<n>`` 형태는 그 시절의 잔재이며, 현재 코드는
# 항상 ``bestin_doorlock_<n>_1`` 로 고정합니다 (iparkapp._dispatch_status).
# v1.4.11: the doorlock unique_id used to follow whichever unit_num spelling
# the server returned. ``bestin_doorlock_<n>_doorlock<n>`` is a leftover from
# that; current code pins it to ``bestin_doorlock_<n>_1``.
_LEGACY_DOORLOCK_SUBTYPE_RE = re.compile(
    rf"^bestin_doorlock_\d+_doorlock\d*{_HASH_SUFFIX}$"
)

# v1.4.11 — 'Heating supply' 센서 제거. 값의 의미가 확인된 적 없고 상수에
# 고정되어 있었습니다 (const.ENERGY_FRIENDLY_LABELS 주석 참고).
# v1.4.11: the "Heating supply" sensor is gone — an unconfirmed guess that in
# practice never moved off a constant (see const.ENERGY_FRIENDLY_LABELS).
_LEGACY_HEAT_SUPPLY_RE = re.compile(
    rf"^bestin_energy_\d+_heat_supply(_\d+)?{_HASH_SUFFIX}$"
)


def _remove_entities_matching(
    hass: HomeAssistant,
    entry: ConfigEntry,
    pattern: re.Pattern[str],
    domain: str | None = None,
) -> list[str]:
    """``unique_id`` 가 패턴과 일치하는 엔티티를 레지스트리에서 제거합니다.

    Remove this config entry's registry entries whose ``unique_id`` matches
    ``pattern`` (optionally restricted to one platform domain). Returns the
    removed entity_ids so callers can log something specific.
    """
    registry = er.async_get(hass)
    removed: list[str] = []
    for entity_id, ent in list(registry.entities.items()):
        if ent.config_entry_id != entry.entry_id:
            continue
        if domain is not None and ent.domain != domain:
            continue
        if not pattern.match(ent.unique_id or ""):
            continue
        registry.async_remove(entity_id)
        removed.append(entity_id)
    return removed


def _remove_device_if_empty(hass: HomeAssistant, identifier: tuple[str, str]) -> bool:
    """엔티티가 하나도 남지 않은 디바이스 항목을 제거합니다.

    Drop a device registry entry once nothing references it any more. HA does
    not garbage-collect devices that still belong to a live config entry, so an
    emptied device would otherwise sit on the integration page forever showing
    no entities.
    """
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={identifier})
    if device is None:
        return False
    ent_reg = er.async_get(hass)
    if er.async_entries_for_device(ent_reg, device.id, include_disabled_entities=True):
        return False
    dev_reg.async_remove_device(device.id)
    return True


def _cleanup_legacy_doorlock_subtype(
    hass: HomeAssistant, entry: ConfigEntry, hub: BestinHub
) -> None:
    """v1.4.11 마이그레이션: 유령 'BESTIN Door Lock' 디바이스를 제거합니다.

    도어락 상태는 허브 디바이스의 ``binary_sensor.*_door_lock`` 이 이미 정상
    보고하고 있습니다. 그 옆에 있던 별도 'BESTIN Door Lock' 디바이스는 예전
    unique_id 규칙에서 만들어진 뒤 다시 채워지지 않아, 'unavailable' 엔티티
    하나만 담은 채 남아 있었습니다.

    v1.4.11 migration: remove the ghost "BESTIN Door Lock" device. The working
    doorlock state lives on the hub device as ``binary_sensor.*_door_lock``;
    the separate device group was minted under an older unique_id rule, never
    repopulated, and has been sitting there holding a single permanently
    'unavailable' entity.
    """
    removed = _remove_entities_matching(
        hass, entry, _LEGACY_DOORLOCK_SUBTYPE_RE, Platform.BINARY_SENSOR.value
    )
    # 'doorlock:doorlock' → device.py 의 formatted_name() 이 만들던 식별자.
    # The device identifier device.py's formatted_name() produced for the
    # 'doorlock:doorlock' sub-type.
    device_gone = _remove_device_if_empty(
        hass, (DOMAIN, f"{hub.wp_version}_Doorlock")
    )
    if removed or device_gone:
        LOGGER.info(
            "v1.4.11 마이그레이션: 유령 도어락 엔티티 %d개 / 디바이스 %s 제거 / "
            "Removed %d orphaned doorlock entities%s.",
            len(removed),
            "제거됨" if device_gone else "없음",
            len(removed),
            " and the empty 'BESTIN Door Lock' device" if device_gone else "",
        )


def _cleanup_heat_supply_sensors(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """v1.4.11 마이그레이션: 'Heating supply' 센서를 제거합니다.

    v1.4.11 migration: drop the "Heating supply" sensor. It was a guess at what
    the wallpad reports beyond its controllable rooms and never moved off a
    constant value, so it is no longer created.
    """
    removed = _remove_entities_matching(
        hass, entry, _LEGACY_HEAT_SUPPLY_RE, Platform.SENSOR.value
    )
    if removed:
        LOGGER.info(
            "v1.4.11 마이그레이션: 'Heating supply' 센서 %d개 제거 / "
            "Removed %d 'Heating supply' sensor(s) — the reading was an "
            "unconfirmed guess pinned to a constant value.",
            len(removed),
            len(removed),
        )


def _merge_main_device_into_hub(
    hass: HomeAssistant, entry: ConfigEntry, hub: BestinHub, hub_device_id: str
) -> None:
    """v1.4.11 마이그레이션: 중복된 'BESTIN' 디바이스를 허브로 합칩니다.

    v1.4.10 까지 MAIN_DEVICES 엔티티(도어락 / 외출 모드 / 환기)는 허브와 이름이
    같은 별도 디바이스에 붙었습니다. 그래서 통합 페이지에 'BESTIN' 이 두 개
    보였고, 그중 허브 쪽은 엔티티 없이 자식 디바이스 링크만 나열했습니다.
    엔티티를 허브 디바이스로 옮긴 뒤 빈 껍데기를 지웁니다. 디바이스를 먼저
    지우면 딸린 엔티티 레지스트리 항목까지 함께 사라져 사용자의 이름 변경 /
    영역 지정 / 비활성화 설정을 잃게 되므로, 순서가 중요합니다.

    v1.4.11 migration: fold the duplicate "BESTIN" device into the hub device.
    Through v1.4.10 the MAIN_DEVICES entities (doorlock / away mode /
    ventilation) attached to a device entry that shared the hub's name, so the
    integration page listed "BESTIN" twice — and the hub copy held no entities,
    rendering as nothing but links to its children. Reassign the entities
    first, then delete the emptied entry: removing the device first would take
    its entity registry entries with it, losing user renames, area assignments
    and enable/disable state.
    """
    dev_reg = dr.async_get(hass)
    legacy = dev_reg.async_get_device(
        identifiers={(DOMAIN, f"{hub.wp_version}_{hub.model}")}
    )
    if legacy is None or legacy.id == hub_device_id:
        return

    ent_reg = er.async_get(hass)
    moved = 0
    for ent in er.async_entries_for_device(
        ent_reg, legacy.id, include_disabled_entities=True
    ):
        ent_reg.async_update_entity(ent.entity_id, device_id=hub_device_id)
        moved += 1

    # 사용자가 지정한 영역 / 이름은 살아남는 쪽으로 옮깁니다 (허브 쪽에 이미
    # 값이 있으면 건드리지 않습니다).
    # Carry the user's area/name over to the surviving entry, without
    # overwriting anything already set on the hub device.
    hub_device = dev_reg.async_get(hub_device_id)
    updates: dict[str, str] = {}
    if legacy.area_id and hub_device is not None and not hub_device.area_id:
        updates["area_id"] = legacy.area_id
    if legacy.name_by_user and hub_device is not None and not hub_device.name_by_user:
        updates["name_by_user"] = legacy.name_by_user
    if updates:
        dev_reg.async_update_device(hub_device_id, **updates)

    dev_reg.async_remove_device(legacy.id)
    LOGGER.info(
        "v1.4.11 마이그레이션: 중복 'BESTIN' 디바이스 통합 (엔티티 %d개 이동) / "
        "Merged the duplicate 'BESTIN' device into the hub device "
        "(%d entities moved).",
        moved,
        moved,
    )


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
    #
    # v1.4.11 부터 이 디바이스는 단순한 부모 노드가 아니라, 세대에 하나뿐인
    # 장치(도어락 / 외출 모드 / 환기)를 직접 담습니다 — device.py 참고.
    # Since v1.4.11 this entry is not just a parent node: the one-per-home
    # devices (doorlock / away mode / ventilation) live directly on it. See
    # device.py.
    device_registry = dr.async_get(hass)
    hub_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, str(hub.hub_id))},
        manufacturer="HDC Labs Co., Ltd.",
        model=hub.wp_version,
        name=hub.name,
        sw_version=hub.sw_version,
    )

    # 허브 디바이스가 존재해야 실행할 수 있는 v1.4.11 정리 작업들.
    # v1.4.11 cleanups — these need the hub device to exist first.
    _merge_main_device_into_hub(hass, entry, hub, hub_device.id)
    _cleanup_legacy_doorlock_subtype(hass, entry, hub)
    _cleanup_heat_supply_sensors(hass, entry)

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


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """UI 에서 디바이스를 직접 삭제할 수 있도록 허용합니다.

    월패드에서 사라진 장치나 예전 버전이 남긴 디바이스 항목을, 통합을 다시
    설정하지 않고도 사용자가 삭제할 수 있게 합니다. 아직 살아 있는 장치라면
    다음 폴링에서 다시 나타납니다.

    Let users delete a device from the UI. Without this hook HA greys the
    delete button out, so stale entries left by older versions (or hardware
    that is genuinely gone) can only be cleared by removing and re-adding the
    whole integration. Anything still reported by the wallpad simply comes
    back on the next poll.
    """
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
