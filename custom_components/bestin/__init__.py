"""The BESTIN component."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_point_in_time

from .const import DOMAIN, LOGGER, PLATFORMS, CONF_SESSION
from .hub import BestinHub
from .iparkapp_const import CONF_IPARKAPP_SITE
from .pwm import PRESET_BOOST, PRESET_COMFORT, PRESET_VACATION


# 휴가 모드 서비스 — Vacation-window service.
SERVICE_SET_VACATION = "set_vacation_window"
SET_VACATION_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,  # if omitted: all climate entities
        vol.Required("start"): cv.datetime,
        vol.Required("end"): cv.datetime,
        vol.Optional("pre_warm_hours", default=2): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=24)
        ),
        vol.Optional("vacation_preset", default=PRESET_VACATION): cv.string,
        vol.Optional("recovery_preset", default=PRESET_BOOST): cv.string,
        vol.Optional("return_preset", default=PRESET_COMFORT): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the BESTIN integration."""
    hub = BestinHub(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

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

    # 첫 entry 가 로드될 때만 서비스를 등록합니다.
    # Register the service only on the first entry load.
    if not hass.services.has_service(DOMAIN, SERVICE_SET_VACATION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_VACATION,
            _make_vacation_handler(hass),
            schema=SET_VACATION_SCHEMA,
        )

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
        # 마지막 entry 언로드 시 서비스 제거 — Drop the service on last unload.
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_SET_VACATION)

    return unload_ok


def _make_vacation_handler(hass: HomeAssistant):
    """휴가 모드 서비스 핸들러를 만듭니다 — Build the vacation service handler.

    동작 / Behaviour:
      1. ``start`` 시각에 지정된 climate 엔티티(들)를 ``vacation_preset`` 으로 전환.
         At ``start``, switches the targeted climate entity/ies to ``vacation_preset``.
      2. ``end - pre_warm_hours`` 시각에 ``recovery_preset`` (기본 boost) 으로 전환.
         At ``end - pre_warm_hours``, switches to ``recovery_preset`` (default boost).
      3. ``end`` 시각에 ``return_preset`` (기본 comfort) 으로 복원.
         At ``end``, switches to ``return_preset`` (default comfort).

    HA 재시작 시에도 안전하게 동작하도록 절대 시각 트리거를 사용합니다.
    Uses absolute-time triggers, so the schedule survives HA restart provided
    the service is invoked after restart with the same window.
    """

    async def _set_preset(entity_ids: list[str] | None, preset: str) -> None:
        target = {ATTR_ENTITY_ID: entity_ids} if entity_ids else {}
        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            {**target, "preset_mode": preset},
            blocking=False,
        )

    async def _handler(call: ServiceCall) -> None:
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        start: datetime = call.data["start"]
        end: datetime = call.data["end"]
        pre_warm_hours: float = call.data["pre_warm_hours"]
        vacation_preset: str = call.data["vacation_preset"]
        recovery_preset: str = call.data["recovery_preset"]
        return_preset: str = call.data["return_preset"]

        if end <= start:
            LOGGER.warning(
                "Vacation: end (%s) must be after start (%s); ignoring.", end, start
            )
            return

        recovery_at = end - timedelta(hours=pre_warm_hours)
        if recovery_at <= start:
            recovery_at = start  # degenerate: window shorter than pre-warm

        now = datetime.now(start.tzinfo) if start.tzinfo else datetime.now()
        LOGGER.info(
            "휴가 모드 예약 — Vacation: %s → %s; recovery at %s; entities=%s",
            start, end, recovery_at, entity_ids or "<all climate>",
        )

        async def _at_start(_now):
            await _set_preset(entity_ids, vacation_preset)

        async def _at_recovery(_now):
            await _set_preset(entity_ids, recovery_preset)

        async def _at_end(_now):
            await _set_preset(entity_ids, return_preset)

        # 이미 지난 시각이면 즉시 적용 — Apply now if the moment has already passed.
        if start <= now:
            await _at_start(now)
        else:
            async_track_point_in_time(hass, _at_start, start)

        if recovery_at <= now and now < end:
            await _at_recovery(now)
        elif recovery_at > now:
            async_track_point_in_time(hass, _at_recovery, recovery_at)

        if now >= end:
            await _at_end(now)
        else:
            async_track_point_in_time(hass, _at_end, end)

    return _handler
