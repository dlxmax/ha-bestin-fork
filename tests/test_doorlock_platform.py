"""Offline test: the door lock is back on its pre-fork platform.

RS-485 and cloud register a switch and send the same commands as upstream
commit 34df0cd. The iPark app, which did not exist upstream and has no control
endpoint, stays a read-only binary_sensor. The registry cleanup must remove only
the entry on the platform a gateway no longer uses, since it runs on every start.

Loads the real const.py, controller.py, center.py, iparkapp.py and __init__.py
with stubbed Home Assistant modules.
"""

import asyncio
import enum
import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.join(ROOT, "custom_components", "bestin")


class _Platform(enum.Enum):
    BINARY_SENSOR = "binary_sensor"
    CLIMATE = "climate"
    FAN = "fan"
    LIGHT = "light"
    SENSOR = "sensor"
    SWITCH = "switch"


class _Placeholder(str):
    """A name from a stubbed module; its attributes are placeholders too."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Placeholder(f"{self}.{name}")

    def __call__(self, *args, **kwargs):
        return _Placeholder(self)


class _Stub(types.ModuleType):
    """Any name not set explicitly is a placeholder."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Placeholder(name)


def _module(name, **attrs):
    mod = _Stub(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


for name in (
    "aiohttp",
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.climate",
    "homeassistant.components.climate.const",
    "homeassistant.components.fan",
    "homeassistant.components.light",
    "homeassistant.config_entries",
    "homeassistant.exceptions",
    "homeassistant.helpers",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.dispatcher",
    "homeassistant.helpers.event",
    "homeassistant.helpers.storage",
    "homeassistant.util",
    "homeassistant.util.dt",
    "serial_asyncio_fast",
    "xmltodict",
):
    _module(name)
_module(
    "homeassistant.const",
    Platform=_Platform,
    ATTR_STATE="state",
    WIND_SPEED="wind_speed",
    CONF_PORT="port",
    CONF_USERNAME="username",
    EVENT_HOMEASSISTANT_STOP="stop",
)
_module("homeassistant.core", callback=lambda f: f, HomeAssistant=object, Event=object)


class _Registry:
    """The parts of the entity registry the cleanup uses."""

    def __init__(self, rows):
        self.entities = {
            entity_id: types.SimpleNamespace(
                config_entry_id=entry_id,
                domain=entity_id.split(".")[0],
                unique_id=unique_id,
            )
            for entity_id, entry_id, unique_id in rows
        }

    def async_remove(self, entity_id):
        del self.entities[entity_id]


_registry = _Registry([])
_er = _module("homeassistant.helpers.entity_registry", async_get=lambda hass: _registry)
sys.modules["homeassistant.helpers"].entity_registry = _er
sys.modules["homeassistant.helpers"].device_registry = sys.modules[
    "homeassistant.helpers.device_registry"
]

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
_module("bst.hub", BestinHub=object)
_module("bst.notify")


def _load(name, alias=None):
    alias = alias or f"bst.{name}"
    spec = importlib.util.spec_from_file_location(alias, f"{REPO}/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "bst"
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("const")
_load("iparkapp_const")
_load("errors")
_load("until")
_load("duty_cycle")
controller = _load("controller")
center = _load("center")
iparkapp = _load("iparkapp")
integration = _load("__init__", "bst.integration")

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def checksummed(*head):
    packet = bytearray(head) + b"\x00"
    packet[-1] = _rs485().calculate_checksum(packet)
    return packet


def _rs485(gateway_type="General"):
    ctrl = object.__new__(controller.BestinController)
    ctrl.gateway_type = gateway_type
    ctrl.hub_id = "hub"
    ctrl.devices = {}
    ctrl.entity_groups = {}
    ctrl.timestamp = 0
    ctrl.signals = []
    ctrl.add_device_callback = lambda signal, device: ctrl.signals.append(signal)
    ctrl.queue = asyncio.Queue()
    return ctrl


def status_frame(state_byte):
    # Layout from parse_doorlock: a 10-byte 0x41 frame with the state in byte 5.
    return checksummed(0x02, 0x41, 0x82, 0x00, 0x00, state_byte, 0, 0, 0)


# --- RS-485: a status frame creates a switch --------------------------------
ctrl = _rs485()
ctrl.handle_device_packet(status_frame(0xAE))
device = ctrl.devices["bestin_doorlock_0"]
check("RS-485 door lock is a switch", device.domain, "switch")
check("RS-485 notifies the switch platform", ctrl.signals, [const.NEW_SWITCH])
check("RS-485 unique_id is upstream's", device.unique_id, "bestin_doorlock_0")
check("RS-485 state from a status frame", device.info.state, True)
ctrl.handle_device_packet(status_frame(0x00))
check("RS-485 state clears", device.info.state, False)


# --- RS-485: the switch reaches the wire, as upstream sends it ---------------
async def rs485_commands():
    ctrl = _rs485()
    sent = []

    async def send_data(packet):
        sent.append(packet.hex())

    ctrl.send_data = send_data
    for value in (True, False):
        await ctrl.enqueue_command("bestin_doorlock_0", value)
        await ctrl.send_packet_queue(ctrl.queue.get_nowait())
    return sent


# From running upstream 34df0cd. It ignores the value, so on and off are identical.
check(
    "RS-485 on and off send upstream's packet",
    asyncio.run(rs485_commands()),
    ["0241020001000000004e", "0241020001000000004e"],
)


# --- cloud: same platform, same command per version -------------------------
def cloud_api(version):
    api = object.__new__(center.BestinCenterAPI)
    api.version = version
    api.hub_id = "hub"
    api.devices = {}
    api.entity_groups = {}
    api.signals = []
    api.requests = []
    api.add_device_callback = lambda signal, device: api.signals.append(signal)

    async def request_feature_command(device_type, room_id, unit, value):
        api.requests.append((device_type, room_id, unit, value))

    api.request_feature_command = request_feature_command
    return api


api = cloud_api(const.SMART_HOME_2)
api._parse_common_status("doorlock", 1, "1", "on")
check("cloud door lock is a switch", next(iter(api.devices.values())).domain, "switch")
check("cloud notifies the switch platform", api.signals, [const.NEW_SWITCH])

asyncio.run(api.enqueue_command("bestin_doorlock_1_1", None, switch="on"))
check("cloud v2 sends upstream's command", api.requests, [("doorlock", 1, "switch1", "on")])

api = cloud_api(const.SMART_HOME_1)
asyncio.run(api.enqueue_command("bestin_doorlock_1_1", None, switch="on"))
check("cloud v1 sends nothing, as upstream", api.requests, [])


# --- iPark app: stays read-only ---------------------------------------------
app = object.__new__(iparkapp.BestinIparkAppAPI)
app.hub_id = "hub"
app.devices = {}
app.entity_groups = {}
app.signals = []
app.add_device_callback = lambda signal, device: app.signals.append(signal)
app._set_device("doorlock", 1, "1", True)
device = next(iter(app.devices.values()))
check("iPark door lock stays a binary_sensor", device.domain, "binary_sensor")
check("iPark notifies the binary_sensor platform", app.signals, [const.NEW_BINARY_SENSOR])
check("iPark unique_id is unchanged", device.unique_id, "bestin_doorlock_1_1")
check(
    "only the iPark door lock differs from the shared map",
    {k for k, v in const.IPARKAPP_PLATFORM_MAP.items() if const.DEVICE_PLATFORM_MAP[k] != v},
    {"doorlock"},
)


# --- registry cleanup -------------------------------------------------------
def cleanup(data):
    global _registry
    _registry = _Registry(
        [
            ("switch.bestin_door_lock", "e", "bestin_doorlock_1_1"),
            ("binary_sensor.bestin_door_lock", "e", "bestin_doorlock_1_1"),
            ("binary_sensor.bestin_away_mode", "e", "bestin_mode_1"),
            ("switch.bestin_gas", "e", "bestin_gas_1"),
            ("binary_sensor.other_door_lock", "other", "bestin_doorlock_1_1"),
        ]
    )
    integration._cleanup_stale_doorlock_entities(None, types.SimpleNamespace(entry_id="e", data=data))
    return set(_registry.entities)


UNRELATED = {
    "binary_sensor.bestin_away_mode",
    "switch.bestin_gas",
    "binary_sensor.other_door_lock",
}
check(
    "RS-485 keeps the switch, drops the old binary_sensor",
    cleanup({"host": "1.2.3.4", "port": 8899}),
    UNRELATED | {"switch.bestin_door_lock"},
)
check(
    "cloud keeps the switch, drops the old binary_sensor",
    cleanup({const.CONF_SESSION: {}}),
    UNRELATED | {"switch.bestin_door_lock"},
)
check(
    "iPark keeps the binary_sensor, drops the old switch",
    cleanup({sys.modules["bst.iparkapp_const"].CONF_IPARKAPP_SITE: "x"}),
    UNRELATED | {"binary_sensor.bestin_door_lock"},
)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
