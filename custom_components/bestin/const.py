import logging

from typing import Callable, Any, Set
from dataclasses import dataclass, field

from homeassistant.const import Platform

DOMAIN = "bestin"
NAME = "BESTIN"
VERSION = "1.4.8"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]

LOGGER = logging.getLogger(__package__)

CONF_VERSION = "version"
CONF_VERSION_1 = "version1.0"
CONF_VERSION_2 = "version2.0"
CONF_SESSION = "session"

DEFAULT_PORT = 8899
DEFAULT_MAX_SEND_RETRY = 10
DEFAULT_PACKET_VIEWER = False

DEFAULT_SCAN_INTERVAL = 30

SMART_HOME_1 = "Smart Home 1.0"
SMART_HOME_2 = "Smart Home 2.0"

SPEED_INT_LOW = 1
SPEED_INT_MEDIUM = 2
SPEED_INT_HIGH = 3

SPEED_STR_LOW = "low"
SPEED_STR_MEDIUM = "mid"
SPEED_STR_HIGH = "high"

PRESET_NONE = "none"
PRESET_NV = "natural_ventilation"

BRAND_PREFIX = "bestin"

NEW_BINARY_SENSOR = "binary_sensors"
NEW_CLIMATE = "climates"
NEW_FAN = "fans"
NEW_LIGHT = "lights"
NEW_SENSOR = "sensors"
NEW_SWITCH = "switchs"

MAIN_DEVICES: list[str] = [
    "fan",
    "ventil",
    "elevator:direction",
    "elevator:floor",
    "gas",
    "doorlock",
    "elevator",
    "mode",
]

PLATFORM_SIGNAL_MAP = {
    Platform.BINARY_SENSOR.value: NEW_BINARY_SENSOR,
    Platform.CLIMATE.value: NEW_CLIMATE,
    Platform.FAN.value: NEW_FAN,
    Platform.LIGHT.value: NEW_LIGHT,
    Platform.SENSOR.value: NEW_SENSOR,
    Platform.SWITCH.value: NEW_SWITCH,
}

DEVICE_PLATFORM_MAP = {
    "temper": Platform.CLIMATE.value,
    "thermostat": Platform.CLIMATE.value,
    "fan": Platform.FAN.value,
    "ventil": Platform.FAN.value,
    "light": Platform.LIGHT.value,
    "light:dcvalue": Platform.SENSOR.value,
    "smartlight": Platform.LIGHT.value,
    "livinglight": Platform.LIGHT.value,
    "outlet": Platform.SWITCH.value,
    "outlet:cutvalue": Platform.SENSOR.value,
    "outlet:standbycut": Platform.SWITCH.value,
    "outlet:powercons": Platform.SENSOR.value,
    "energy": Platform.SENSOR.value,
    "doorlock": Platform.BINARY_SENSOR.value,
    "elevator": Platform.SWITCH.value,
    "elevator:direction": Platform.SENSOR.value,
    "elevator:floor": Platform.SENSOR.value,
    # 외출(away) 모드 — iparkapp 게이트웨이에서만 노출됨.  서버는 "normal" /
    # "unoccupied" 두 상태를 ``remote_access_mode`` 로 보고하며, 활성화 명령
    # ``unoccupied`` 만 받습니다 (해제는 키패드의 비밀번호 입력이 필요한
    # 보안 모델). v1.4.6: 읽기 전용 binary_sensor 로 노출. arm 버튼은 v1.4.7
    # 이후 별도 platform 추가 검토 예정.
    # iparkapp-only away/alarm-arm state. Server reports "normal" or
    # "unoccupied" via ``remote_access_mode`` and accepts only the arm
    # command — disarming requires the keypad passcode by design. Exposed
    # read-only here; a separate arm button is on the v1.4.7+ shortlist.
    "mode": Platform.BINARY_SENSOR.value,
    "electric": Platform.SWITCH.value,
    "electric:standbycut": Platform.SWITCH.value,
    "gas": Platform.SWITCH.value,
    # 도어락은 '잠김/해제' 상태만 정확히 노출됩니다. iPark 앱 게이트웨이는 제어
    # 명령을 지원하지 않고, RS-485 게이트웨이의 제어 패킷도 검증되지 않았습니다.
    # Doorlock state is only reliably reported, not controlled. The iPark App
    # gateway exposes no control endpoint, and the RS-485 doorlock packet is
    # unverified — so this is safest as a binary_sensor (locked / unlocked).
    # 'unit_cnt' 를 초과해 응답되는 추가 난방 온도 센서. 구체적 의미는 단지마다
    # 상이하며, 지역난방 공급 온도일 수 있으나 확인되지 않았습니다.
    # Extra heat-temperature reading the wallpad reports beyond the household's
    # controllable rooms (rooms past `status_map.unit_cnt`). Exact meaning
    # varies by complex — possibly a district-heating supply temp, possibly
    # something else; not confirmed.
    "heatsource": Platform.SENSOR.value,
}

# 친근한 표시명 — Friendly display names for HA entities. The internal
# device_type strings (e.g. ``livinglight``, ``temper``) stay stable so that
# device-registry identifiers and unique_ids do not drift across versions;
# this map is consulted only for what HA shows on screen.
FRIENDLY_TYPE_NAMES: dict[str, str] = {
    "livinglight": "Light",
    "light": "Light",
    "smartlight": "Light",
    "electric": "Outlet",
    "outlet": "Outlet",
    "temper": "Thermostats",
    "thermostat": "Thermostats",
    "gas": "Gas Valve",
    "fan": "Ventilation",
    "ventil": "Ventilation",
    "mode": "Away Mode",
    "doorlock": "Door Lock",
    # 'heatsource' removed in v1.4.3 — those readings now live under
    # BESTIN Energy as 'Heating supply' (see ENERGY_FRIENDLY_LABELS).
    "energy": "Energy",
    "elevator": "Elevator",
}

# 엔티티 표시명 단순화 — v1.4.3.
# Per-entity name simplification rules used by iparkapp.py's _initial_device.
# Single-room types: device_room is always "1" (e.g. living-room lights, the
# household-wide energy meters), so prepending it to the entity name is noise.
SINGLE_ROOM_TYPES: set[str] = {"livinglight", "energy", "smartlight"}
# Single-channel types: sub_id is always "1" (or duplicates device_room), so
# the trailing index is noise too.
SINGLE_CHANNEL_TYPES: set[str] = {"doorlock", "gas", "fan", "ventil"}

# 친근한 에너지 라벨 — Friendly per-sub_id labels for BESTIN Energy entities.
# The raw sub_ids ("avg_elec", "mine_gas", "hwater" ...) come straight from
# the iparkapp REST payload and are cryptic in HA. Map them to readable
# English. Two axes: "mine_*" is the household reading, "avg_*" is the
# complex-wide neighbor average. "heat_supply" is the floor-heating supply
# temperature reading the cloud server reports above unit_cnt (formerly the
# orphan "BESTIN Heat Sensor" device entry, now folded in here).
ENERGY_FRIENDLY_LABELS: dict[str, str] = {
    "mine_elec":   "Electricity",
    "avg_elec":    "Neighbor avg electricity",
    "mine_gas":    "Gas",
    "avg_gas":     "Neighbor avg gas",
    "mine_water":  "Water",
    "avg_water":   "Neighbor avg water",
    "mine_hwater": "Hot water",
    "avg_hwater":  "Neighbor avg hot water",
    "mine_heat":   "Heating",
    "avg_heat":    "Neighbor avg heating",
    "heat_supply": "Heating supply",
}


@dataclass
class DeviceInfo:
    """Represents information about a device."""
    device_type: str
    name: str
    room: str
    state: Any
    device_id: str

@dataclass
class DeviceProfile:
    """Manages device profiles, including callbacks and command handling."""
    enqueue_command: Callable[..., None]
    domain: str
    unique_id: str
    info: DeviceInfo
    callbacks: Set[Callable[..., None]] = field(default_factory=set)

    def add_callback(self, callback: Callable[..., None]) -> None:
        """Adds a callback to the set of callbacks."""
        self.callbacks.add(callback)

    def remove_callback(self, callback: Callable[..., None]) -> None:
        """Removes a callback from the set of callbacks."""
        self.callbacks.discard(callback)
    
    def update_callbacks(self) -> None:
        """Calls all registered callbacks."""
        for callback in self.callbacks:
            assert callable(callback), "Callback should be callable"
            callback()
