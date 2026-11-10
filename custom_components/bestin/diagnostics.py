"""BESTIN 진단 / Diagnostics for BESTIN.

설정 > 기기 및 서비스 > BESTIN > ⋮ > 진단 다운로드. 비밀번호, 아이디, IP,
좌표, 세션, 세대 동·호는 가립니다. 단지 코드와 단지 이름은 단지별 서버 차이를
가려내는 데 필요해서 남깁니다.

Settings > Devices & services > BESTIN > ⋮ > Download diagnostics. Passwords,
user IDs, IPs, coordinates, sessions and the household unit are redacted. The
complex code and name stay: they are how we tell one complex's server from
another.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .const import CONF_SESSION, DOMAIN
from .iparkapp_const import CONF_IPARKAPP_SITE
from .report import (
    LOG_RING,
    SETUP_ERRORS_KEY,
    TO_REDACT,
    build_issue_url,
    build_summary_blocks,
    collect_secrets,
    issue_title,
    scrub_obj,
)

def gateway_kind(entry: ConfigEntry) -> str:
    """연결 방식 이름 / Short name of the connection type."""
    if CONF_IPARKAPP_SITE in entry.data:
        return "iparkapp"
    if CONF_SESSION not in entry.data:
        return "rs485"
    if "username" in entry.data:
        return "center_v1"
    return "center_v2"


async def integration_version(hass: HomeAssistant) -> str | None:
    """manifest.json 의 버전 / Version from manifest.json."""
    try:
        integration = await async_get_integration(hass, DOMAIN)
    except Exception:  # noqa: BLE001 / diagnostics must never fail
        return None
    return str(integration.version) if integration.version else None


def _gateway_snapshot(hub: Any) -> dict[str, Any]:
    api = getattr(hub, "api", None)
    snapshot: dict[str, Any] = {}
    if api is not None and hasattr(api, "diagnostics_snapshot"):
        try:
            snapshot = api.diagnostics_snapshot()
        except Exception as ex:  # noqa: BLE001
            snapshot = {"snapshot_error": f"{type(ex).__name__}: {ex}"}
    connection = getattr(hub, "connection", None)
    if connection is not None:
        snapshot.setdefault("kind", "rs485")
        snapshot["hub_gateway_mode"] = getattr(hub, "gateway_mode", None)
        try:
            snapshot.setdefault("connected", connection.is_connected())
        except Exception:  # noqa: BLE001
            pass
        snapshot.setdefault("reconnect_attempts", getattr(connection, "reconnect_attempts", None))
    return snapshot


def _devices(hub: Any) -> list[dict[str, Any]]:
    devices = getattr(getattr(hub, "api", None), "devices", None) or {}
    out = []
    for device_id, profile in sorted(devices.items()):
        info = getattr(profile, "info", None)
        out.append(
            {
                "device_id": device_id,
                "domain": getattr(profile, "domain", None),
                "device_type": getattr(info, "device_type", None),
                "room": getattr(info, "room", None),
                "state": repr(getattr(info, "state", None))[:300],
            }
        )
    return out


def _entities(hass: HomeAssistant, entry: ConfigEntry) -> tuple[dict, list]:
    registry = er.async_get(hass)
    counts: dict[str, dict[str, int]] = {}
    rows: list[dict[str, Any]] = []
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        state = hass.states.get(ent.entity_id)
        value = state.state if state is not None else None
        bucket = counts.setdefault(ent.domain, {"total": 0, "unavailable": 0, "disabled": 0})
        bucket["total"] += 1
        if ent.disabled_by is not None:
            bucket["disabled"] += 1
        elif value in (None, "unavailable"):
            bucket["unavailable"] += 1
        rows.append(
            {
                "entity_id": ent.entity_id,
                "state": value,
                "disabled": ent.disabled_by is not None,
            }
        )
    return counts, rows


async def async_collect(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """가린 진단 데이터 전체 / The full, redacted diagnostics data."""
    secrets = collect_secrets(
        entry.data, {"unique_id": entry.unique_id, "title": entry.title}
    )
    hub = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    site = entry.data.get(CONF_IPARKAPP_SITE) or {}
    counts, entity_rows = _entities(hass, entry)
    snapshot: dict[str, Any] = {
        "integration": {
            "version": await integration_version(hass),
            "ha_version": HA_VERSION,
            "gateway": gateway_kind(entry),
            "site": " ".join(
                str(v) for v in (site.get("sitecode"), site.get("sitename")) if v
            ) or None,
            "entry_state": getattr(entry.state, "value", str(entry.state)),
        },
        "setup_error": hass.data.get(SETUP_ERRORS_KEY, {}).get(entry.entry_id),
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "gateway": _gateway_snapshot(hub) if hub is not None else {},
        "entities": counts,
        "entity_states": entity_rows,
        "devices": _devices(hub),
        "log": list(LOG_RING.records),
    }
    return scrub_obj(snapshot, secrets)


async def async_build_report(
    hass: HomeAssistant, entry: ConfigEntry, user_text: str
) -> tuple[str, str]:
    """문제 신고 링크와 본문 / The problem-report link and its body."""
    snapshot = await async_collect(hass, entry)
    secrets = collect_secrets(
        entry.data, {"unique_id": entry.unique_id, "title": entry.title}
    )
    user_text = scrub_obj(user_text or "", secrets)
    info = snapshot["integration"]
    title = issue_title(info.get("gateway"), info.get("version"), user_text)
    return build_issue_url(title, user_text, build_summary_blocks(snapshot))


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    snapshot = await async_collect(hass, entry)
    return {"summary": "\n\n".join(build_summary_blocks(snapshot)), **snapshot}
