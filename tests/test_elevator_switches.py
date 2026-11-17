"""Offline test for issue #8: elevator down and up switches, and the floor and
direction sensors when the server refuses the status stream.

  1. Center v2 registers the per-car down switches with the same unique ids
     as before, plus one "Elevator up" switch.
  2. The down switches send "down"; the up switch sends "up" (the official
     app, com.mobiletalk.valley 1.5.4, calls /v2/api/elevator/{up|down}).
  3. The down switches are named "Elevator down", numbered when there is more
     than one elevator (#2); the new one is "Elevator up".
  4. Floor and direction sensors are unavailable only while the server
     refuses the stream; other sensors are unaffected.

Loads the real const.py, center.py, device.py, switch.py and sensor.py with
stubbed Home Assistant modules. Run with: python3 tests/test_elevator_switches.py
"""

import asyncio
import enum
import importlib.util
import os
import sys
import types

REPO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "custom_components",
    "bestin",
)


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


class _Entity:
    @property
    def available(self):
        return True


class _DeviceInfo(dict):
    __annotations__ = {}


for name in (
    "aiohttp",
    "xmltodict",
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.climate",
    "homeassistant.components.climate.const",
    "homeassistant.components.fan",
    "homeassistant.components.light",
    "homeassistant.config_entries",
    "homeassistant.helpers",
    "homeassistant.helpers.dispatcher",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.event",
):
    _module(name)
_module(
    "homeassistant.const",
    Platform=_Platform,
    STATE_ON="on",
    STATE_OFF="off",
    ATTR_STATE="state",
    WIND_SPEED="wind_speed",
)
_module("homeassistant.core", callback=lambda f: f, HomeAssistant=object)
_module("homeassistant.helpers.entity", Entity=_Entity)
_module("homeassistant.helpers.device_registry", DeviceInfo=_DeviceInfo)
_module("homeassistant.components.sensor", SensorEntity=_Entity, DOMAIN="sensor")
_module("homeassistant.components.switch", SwitchEntity=_Entity, DOMAIN="switch")

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
_module("bst.hub", BestinHub=object)


def _load(name):
    spec = importlib.util.spec_from_file_location(f"bst.{name}", f"{REPO}/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "bst"
    sys.modules[f"bst.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("const")
_load("until")
center = _load("center")
_load("device")
switch = _load("switch")
sensor = _load("sensor")

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


# --- registration, as _v2_device_status does it ------------------------------
api = object.__new__(center.BestinCenterAPI)
api.version = const.SMART_HOME_2
api.hub_id = "hub"
api.devices = {}
api.entity_groups = {}
api.add_device_callback = lambda signal, device: None
api.elevator_sse_refused = False
api.elevator_number = 2
for car in ("1", "2"):
    api._elevator_registration(car)
api.set_device("elevator", 1, "up", False)

switches = {k: v for k, v in api.devices.items() if v.domain == "switch"}
check("switch ids", sorted(switches),
      ["bestin_elevator_1_1", "bestin_elevator_1_2", "bestin_elevator_1_up"])
check("down switch unique id unchanged", switches["bestin_elevator_1_1"].unique_id,
      "bestin_elevator_1_1")
check("up switch unique id", switches["bestin_elevator_1_up"].unique_id,
      "bestin_elevator_1_up")
check("up switch type", switches["bestin_elevator_1_up"].info.device_type, "elevator:up")

# --- each switch sends its direction ------------------------------------------
sent = []


async def fake_call(direction="down"):
    sent.append(direction)


api.elevator_call_request = fake_call
for dev_id in sorted(switches):
    asyncio.run(api.enqueue_command(dev_id, None, switch="on"))
check("switch directions", sent, ["down", "down", "up"])

# --- names and icons -----------------------------------------------------------
hub = types.SimpleNamespace(
    api=api,
    available=True,
    entity_groups={"switch": set(), "sensor": set()},
    hub_id="hub",
)
for dev_id, name, icon in (
    ("bestin_elevator_1_1", "Elevator down 1", "mdi:elevator-down"),
    ("bestin_elevator_1_2", "Elevator down 2", "mdi:elevator-down"),
    ("bestin_elevator_1_up", "Elevator up", "mdi:elevator-up"),
):
    entity = switch.BestinSwitch(switches[dev_id], hub)
    check(f"{dev_id} name (2 elevators)", entity._attr_name, name)
    check(f"{dev_id} icon", entity._attr_icon, icon)

# One elevator: no number, it is the only down switch.
api.elevator_number = 1
check("single elevator name",
      switch.BestinSwitch(switches["bestin_elevator_1_1"], hub)._attr_name, "Elevator down")
check("up switch has no number",
      switch.BestinSwitch(switches["bestin_elevator_1_up"], hub)._attr_name, "Elevator up")
api.elevator_number = 2

# --- floor/direction availability follows the stream --------------------------
floor = sensor.BestinSensor(api.devices["bestin_elevator_1_floor_1"], hub)
direction = sensor.BestinSensor(api.devices["bestin_elevator_1_direction_2"], hub)
check("floor available while the stream works", floor.available, True)
api.elevator_sse_refused = True
check("floor unavailable while refused", floor.available, False)
check("direction unavailable while refused", direction.available, False)
other = types.SimpleNamespace(
    info=types.SimpleNamespace(
        device_type="energy:mineelec", device_id="bestin_energy_1_mine_elec",
        name="x", room="1", state=1,
    ),
    unique_id="bestin_energy_1_mine_elec",
)
check("other sensors unaffected", sensor.BestinSensor(other, hub).available, True)
api.elevator_sse_refused = False
check("floor back when accepted", floor.available, True)
hub.available = False
check("hub down still wins", floor.available, False)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
