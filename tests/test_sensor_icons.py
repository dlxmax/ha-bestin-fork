"""Offline test: RS-485 and iPark app meters get the same default icons.

An RS-485 meter's device_type is a bare "energy", so a DEVICE_ICON lookup by
device_type alone finds nothing (true since v1.4.10). Its icon has to come from
the device_id instead.

Builds the RS-485 devices with the real controller.py and reads the icons from
the real sensor.py, with stubbed Home Assistant modules.
"""

import enum
import importlib.util
import json
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
        return _Placeholder(name)


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


class _SensorEntity:
    pass


class _BestinDevice:
    def __init__(self, device, hub):
        self._device_info = device.info


for name in (
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
):
    _module(name)
_module("homeassistant.const", Platform=_Platform)
_module("homeassistant.core", callback=lambda f: f, HomeAssistant=object)
_module("homeassistant.components.sensor", SensorEntity=_SensorEntity)

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
_module("bst.device", BestinDevice=_BestinDevice)
_module("bst.hub", BestinHub=object)


def _load(name):
    spec = importlib.util.spec_from_file_location(f"bst.{name}", f"{REPO}/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"bst.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_load("const")
controller = _load("controller")
sensor = _load("sensor")

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


WANT = {
    "electric": "mdi:home-lightning-bolt",
    "gas": "mdi:gas-burner",
    "heat": "mdi:heating-coil",
    "hotwater": "mdi:thermometer-water",
    "water": "mdi:water",
}


def rs485_icons(gateway_type, packet_len):
    """Feed one energy packet through the real controller, return sensor icons."""
    ctrl = object.__new__(controller.BestinController)
    ctrl.gateway_type = gateway_type
    ctrl.hub_id = "hub"
    ctrl.devices = {}
    ctrl.entity_groups = {}
    ctrl.add_device_callback = lambda signal, device: None
    for meter, state in ctrl.parse_energy(bytearray(packet_len)).items():
        ctrl.set_device(f"energy_{meter}", state, is_sub=True)
    return {
        device.info.device_id: (
            device.info.device_type,
            sensor.BestinSensor(device, None)._attr_icon,
        )
        for device in ctrl.devices.values()
    }


for gateway, packet_len, meters in (
    ("General", 48, ("electric", "water", "hotwater", "gas", "heat")),
    ("AIO", 34, ("electric", "water", "gas")),
):
    icons = rs485_icons(gateway, packet_len)
    check(f"{gateway} creates a total and a realtime sensor per meter", len(icons), len(meters) * 2)
    for meter in meters:
        for kind in ("total", "realtime"):
            device_id = f"bestin_energy_{meter}_{kind}"
            check(f"{gateway} {device_id}", icons[device_id], ("energy", WANT[meter]))

for sub_id, meter in (
    ("elec", "electric"),
    ("gas", "gas"),
    ("heat", "heat"),
    ("hwater", "hotwater"),
    ("water", "water"),
):
    for scope in ("mine", "avg"):
        info = types.SimpleNamespace(
            device_type=f"energy:{scope}{sub_id}",
            device_id=f"bestin_energy_1_{scope}_{sub_id}",
        )
        entity = sensor.BestinSensor(types.SimpleNamespace(info=info), None)
        check(f"iPark app {info.device_type}", entity._attr_icon, WANT[meter])

info = types.SimpleNamespace(device_type="light:dcvalue", device_id="bestin_light_1_dcvalue")
entity = sensor.BestinSensor(types.SimpleNamespace(info=info), None)
check("other sensors keep their icon", entity._attr_icon, "mdi:flash")

with open(f"{REPO}/icons.json", encoding="utf-8") as f:
    thermostat = json.load(f)["entity"]["climate"]["thermostat"]
check("thermostat default icon", thermostat["default"], "mdi:thermostat-box")
check(
    "preset dropdown icons unchanged",
    thermostat["state_attributes"]["preset_mode"]["default"],
    "mdi:thermostat",
)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
