"""iPark 스마트홈 앱 — Constants and device-class table.

iPark Smarthome App method talks to a per-complex central PHP server (e.g.
``220.79.141.134``) the way the official Android WebView app does. See
``temp/PROTOCOL_FINDINGS.md`` (gitignored) for the reverse-engineered details.

이 모듈은 신규 'iPark 스마트홈 앱' 연동을 위한 상수와 장치 클래스 표를 정의합니다.
This module declares the constants and the device-class table used by the
new "iPark Smarthome App" gateway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# 단지(아파트) 디렉터리 — Complex (apartment) directory
DIRECTORY_URL = "http://www.i-parklife.com/service/getSiteIPARKList.php?is_utf=1"

# 신규 연동 식별자 — Identifier for the new gateway type
GATEWAY_TYPE_IPARKAPP = "iparkapp"
SMART_HOME_APP = "iPark 스마트홈 앱 / iPark Smarthome App"

# config_entry.data 에 저장될 키 — Keys persisted into ``ConfigEntry.data``
CONF_IPARKAPP_SITE = "iparkapp_site"
CONF_IPARKAPP_USERNAME = "iparkapp_username"
CONF_IPARKAPP_PASSWORD = "iparkapp_password"
# config_entry.options 에 저장될 키 — Keys persisted into ``ConfigEntry.options``
CONF_PWM_MODE = "pwm_mode"  # off / eco / comfort / boost

# CONF_IPARKAPP_SITE 값은 dict 형태로 저장되며 다음 필드를 포함합니다.
# The ``iparkapp_site`` value is stored as a dict with the following fields,
# matching the upstream directory schema (with normalised key names):
#
#   {
#     "sitecode":   "0051",            # SITECODE
#     "sitename":   "남양주 별내",     # SITENAME (human-readable)
#     "ip":         "220.79.141.134",  # NETW_ADDR
#     "weather":    "4136031000",      # SITEWEATHER (passed to login)
#     "lat":        "127.1187887",     # LAT field as-returned by directory
#     "lng":        "37.6629579",      # LNG field as-returned by directory
#   }
#
# 디렉터리에서 일부 단지의 LAT/LNG 필드가 서로 뒤바뀌어 있는 것이 확인되었습니다.
# 앱처럼 그대로 전송합니다.
# Note: some directory entries have LAT/LNG fields swapped. We pass them
# through verbatim to match the official app's behaviour.


# 서버 엔드포인트 — Server endpoints (relative to ``http://{IP}/``)
LOGIN_LANDING_PATH = "/webapp/login_chk_webapp.php"
LOGIN_DATA_PATH = "/webapp/data/getLoginWebApp.php"
INDEX_PATH = "/webapp/index.php"
DEVICE_PATH = "/webapp/data/getHomeDevice.php"
HEAT_PATH = "/webapp/data/getHomeDevice_heat.php"
ENERGY_PATH_TEMPLATE = "/webapp/data/getEnergyAvr_monthly_{kind}.php"

# AJAX 요청 헤더 (반드시 필요) — Required AJAX headers.
# 'X-Requested-With' 헤더가 없으면 서버는 즉시 'timeout' 더미 응답을 반환합니다.
# Without ``X-Requested-With: XMLHttpRequest`` the server short-circuits every
# device call with a stub ``result="timeout"`` response. Mandatory.
AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# 모바일 브라우저 User-Agent (앱 WebView 흉내) — Mobile UA mimicking the WebView.
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/110.0.0.0 Mobile Safari/537.36"
)

# 서버 result 값 — Server result vocabulary returned in <service result="...">.
RESULT_OK = "ok"
RESULT_ERRORS_RETRYABLE = ("timeout", "connect_fail", "send_fail", "recv_fail")
RESULT_ERRORS_FATAL = ("deny", "fail")


# 기본 폴링 간격 — Default poll interval (seconds). 30s matches the existing
# integration default. Override via the integration's options flow.
DEFAULT_POLL_INTERVAL = 30

# 세션 갱신 간격 — Session refresh interval (minutes). Matches v1 cadence.
DEFAULT_SESSION_REFRESH_MINUTES = 15

# 객실 탐색 범위 — Probe range when discovering room-scoped devices.
ROOM_PROBE_RANGE = range(1, 7)

# 친근한 표시명은 const.py 의 FRIENDLY_TYPE_NAMES 로 통합되었습니다 (v1.4.2).
# 모든 게이트웨이가 동일한 표시명을 공유하며, 표시는 device_info 레벨에서만
# 적용되므로 엔티티 unique_id 와 디바이스 식별자는 변하지 않습니다.
# Friendly display names were consolidated into ``const.FRIENDLY_TYPE_NAMES``
# in v1.4.2 so all three gateway paths share the same labels and the mapping
# is applied only at the device_info level (entity unique_ids and the device
# registry identifiers are unchanged).


# Referer 헤더용 페이지 매핑 — Per-class referer page for AJAX fidelity.
# 앱 WebView 가 항상 이런 페이지에서 fetch 호출을 하므로 동일하게 흉내냅니다.
# The WebView always issues device fetches from these pages; we mirror that.
REFERER_PAGES: dict[str, str] = {
    "livinglight": "/webapp/xml_ctrl_light.php",
    "light": "/webapp/xml_ctrl_M_light.php",
    "electric": "/webapp/xml_ctrl_electric.php",
    "temper": "/webapp/xml_ctrl_heat.php",
    "gas": "/webapp/xml_ctrl_gas.php",
    "ventil": "/webapp/xml_ctrl_fan.php",
    "mode": "/webapp/xml_ctrl_goout.php",
    "doorlock": "/webapp/xml_ctrl_door.php",
}


@dataclass(frozen=True)
class DeviceClass:
    """장치 클래스 메타데이터 — Per-device-class metadata.

    Maps a logical device class (e.g. living-room lights) onto the
    server's ``req_name`` plus the URL handler that serves it. Also
    carries the per-class control vocabulary so the client can validate
    outgoing commands cheaply.
    """

    # 내부 식별자 — Internal short name used in logs / device IDs.
    key: str
    # 서버 ``req_name`` — exact value sent in the URL.
    req_name: str
    # PHP handler path on the server.
    path: str
    # 객실별 (room-scoped) ?
    room_scoped: bool = False
    # 'switch{N}' / 'gas1' / 'ventil' / 'null' / 'room{N}' / None
    unit_pattern: str | None = None
    # 제어 동사 어휘 — Allowed control verbs. ``None`` means status-only.
    control_actions: tuple[str, ...] | None = None


# 장치 클래스 테이블 — Device-class table used by the client to drive
# both status polling and control dispatch.
DEVICE_CLASSES: dict[str, DeviceClass] = {
    "livinglight": DeviceClass(
        key="livinglight",
        req_name="remote_access_livinglight",
        path=DEVICE_PATH,
        room_scoped=False,
        unit_pattern="switch{n}",
        control_actions=("on", "off"),
    ),
    "light": DeviceClass(
        key="light",
        req_name="remote_access_light",
        path=DEVICE_PATH,
        room_scoped=True,
        unit_pattern="switch{n}",
        control_actions=("on", "off"),
    ),
    "electric": DeviceClass(
        key="electric",
        req_name="remote_access_electric",
        path=DEVICE_PATH,
        room_scoped=True,
        unit_pattern="switch{n}",
        control_actions=("on", "off", "set", "unset"),
    ),
    "temper": DeviceClass(
        key="temper",
        req_name="remote_access_temper",
        path=HEAT_PATH,  # 별도 핸들러 사용 — separate PHP handler
        room_scoped=False,  # room comes via unit_num pattern instead
        unit_pattern="room{n}",
        control_actions=("on", "off"),  # appended as "{verb}/{temperature}"
    ),
    "gas": DeviceClass(
        key="gas",
        req_name="remote_access_gas",
        path=DEVICE_PATH,
        room_scoped=False,
        unit_pattern="gas1",
        control_actions=("close",),  # 가스밸브는 닫기 전용 — close only
    ),
    "ventil": DeviceClass(
        key="ventil",
        req_name="remote_access_ventil",
        path=DEVICE_PATH,
        room_scoped=False,
        unit_pattern="ventil",
        control_actions=("on", "off", "low", "mid", "high"),
    ),
    "mode": DeviceClass(
        key="mode",
        req_name="remote_access_mode",
        path=DEVICE_PATH,
        room_scoped=False,
        unit_pattern="null",
        control_actions=("unoccupied",),  # 외출 모드 켜기 전용 — set-only
    ),
    "doorlock": DeviceClass(
        key="doorlock",
        req_name="remote_access_doorlock",
        path=DEVICE_PATH,
        room_scoped=False,
        unit_pattern=None,
        control_actions=None,  # 상태 조회만 — status only
    ),
}


# 에너지 모니터링 카테고리 — Energy monitoring categories.
# Maps the URL ``{kind}`` placeholder onto a stable internal sensor key plus
# bilingual labels. Each ``getEnergyAvr_monthly_{kind}.php`` returns a JSON
# array with two series ("complex average" + "my home") for the last 3 months.
ENERGY_CATEGORIES: dict[str, dict[str, str]] = {
    "Elec":   {"key": "energy_electric",  "ko": "전기",   "en": "Electricity"},
    "Gas":    {"key": "energy_gas",       "ko": "가스",   "en": "Gas"},
    "Heat":   {"key": "energy_heat",      "ko": "난방",   "en": "Heating"},
    "Hwater": {"key": "energy_hot_water", "ko": "온수",   "en": "Hot water"},
    "Water":  {"key": "energy_water",     "ko": "수도",   "en": "Water"},
}


def make_unit_id(cls: DeviceClass, n: int | None = None) -> str:
    """단위 ID를 생성합니다 — Build the ``req_unit_num`` value for a class.

    For numbered patterns like ``switch{n}`` or ``room{n}`` we substitute
    the room/switch index. For static patterns (``gas1``, ``ventil``,
    ``null``) we return as-is. ``None`` for classes with no unit_num.
    """
    if cls.unit_pattern is None:
        return ""
    if "{n}" in cls.unit_pattern:
        if n is None:
            raise ValueError(f"unit_pattern {cls.unit_pattern!r} requires n")
        return cls.unit_pattern.format(n=n)
    return cls.unit_pattern


def normalize_status(value: str) -> Any:
    """장치 상태를 표준화합니다 — Normalise a raw ``unit_status`` string.

    The wallpad uses inconsistent vocab (e.g. control verb is ``mid`` but
    status echoes ``middle``). We collapse those here so downstream entity
    code only sees one canonical form.
    """
    if value is None:
        return None
    v = value.strip().lower()
    # 환기 속도 — Vent speed normalisation
    if v == "middle":
        return "mid"
    # boolean-ish values (lights, outlets, fan power, gas valve, away mode)
    if v in ("on", "open", "set", "unoccupied"):
        return True
    if v in ("off", "closed", "close", "unset", "occupied"):
        return False
    return v
