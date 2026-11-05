"""Offline test: RS-485 regressions against upstream v1.1.9 behaviour.

There is no RS-485 hardware to test on, so upstream's output is the reference.
Runs real packets from guide/packet_dump.txt through the real controller.py and
sensor.py. The expected numbers below are what upstream commit 34df0cd produces
for the same packets. Also runs the real async_setup_entry for a new RS-485
install, the real thermostat step for each gateway, and checks the iPark app
keys that v1.4.10 fixed stay fixed.
"""

import asyncio
import enum
import importlib.util
import os
import re
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
    def __init__(self, *args, **kwargs):
        pass


class _BestinDevice:
    def __init__(self, device, hub):
        self._device_info = device.info
        self.hub = hub


class _ColorMode(str, enum.Enum):
    BRIGHTNESS = "brightness"
    COLOR_TEMP = "color_temp"


for name in (
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.fan",
    "homeassistant.config_entries",
    "homeassistant.helpers",
    "homeassistant.helpers.dispatcher",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.restore_state",
    "homeassistant.exceptions",
    "serial_asyncio_fast",
):
    _module(name)
_module(
    "homeassistant.components.climate",
    DOMAIN="climate",
    ClimateEntity=_Entity,
)
_module(
    "homeassistant.components.climate.const",
    SERVICE_SET_TEMPERATURE="set_temperature",
    ATTR_HVAC_MODE="hvac_mode",
    ATTR_PRESET_MODE="preset_mode",
    ATTR_PRESET_MODES="preset_modes",
    ATTR_CURRENT_TEMPERATURE="current_temperature",
    HVACMode=types.SimpleNamespace(HEAT="heat", OFF="off"),
)
_module("homeassistant.components.light", ColorMode=_ColorMode)
_module(
    "homeassistant.components.sensor",
    SensorEntity=_Entity,
)
_module(
    "homeassistant.const",
    Platform=_Platform,
    ATTR_STATE="state",
    WIND_SPEED="wind_speed",
    CONF_PORT="port",
    CONF_USERNAME="username",
    EVENT_HOMEASSISTANT_STOP="stop",
)
_module("homeassistant.core", callback=lambda f: f, HomeAssistant=object, State=object, Event=object)
sys.modules["homeassistant.helpers.restore_state"].RestoreEntity = type("RestoreEntity", (), {})


class _DeviceRegistry:
    def __init__(self):
        self.models = []

    def async_get_or_create(self, **kwargs):
        self.models.append(kwargs["model"])
        return types.SimpleNamespace(id="hub-device")

    def async_get_device_by_identifier(self, identifier, entry_id):
        return None


_device_registry = _DeviceRegistry()
_entity_registry = types.SimpleNamespace(entities={})
_dr = _module("homeassistant.helpers.device_registry", async_get=lambda hass: _device_registry)
_er = _module("homeassistant.helpers.entity_registry", async_get=lambda hass: _entity_registry)
sys.modules["homeassistant.helpers"].device_registry = _dr
sys.modules["homeassistant.helpers"].entity_registry = _er

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
_module("bst.device", BestinDevice=_BestinDevice)
_module("bst.center", BestinCenterAPI=object)
_module("bst.iparkapp", BestinIparkAppAPI=object)
_module("bst.notify")


def _load(name, alias=None):
    alias = alias or f"bst.{name}"
    spec = importlib.util.spec_from_file_location(
        alias, f"{REPO}/{name}.py", submodule_search_locations=None
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "bst"
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("const")
iparkapp_const = _load("iparkapp_const")
_load("errors")
_load("until")
controller = _load("controller")
hub_module = _load("hub")
sensor = _load("sensor")
climate = _load("climate")
integration = _load("__init__", "bst.integration")

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def dump_packets():
    with open(os.path.join(ROOT, "guide", "packet_dump.txt"), encoding="utf-8") as f:
        for line in f:
            digits = re.sub(r"[^0-9a-fA-F]", "", line)
            if digits and len(digits) % 2 == 0:
                yield bytearray.fromhex(digits)


def rs485_sensors(gateway_type):
    ctrl = object.__new__(controller.BestinController)
    ctrl.gateway_type = gateway_type
    ctrl.hub_id = "hub"
    ctrl.devices = {}
    ctrl.entity_groups = {}
    ctrl.timestamp = 0
    ctrl.add_device_callback = lambda signal, device: None
    for packet in dump_packets():
        ctrl.handle_device_packet(packet)
    hub = types.SimpleNamespace(wp_version=f"{gateway_type}-generation")
    return {
        device.info.device_id: sensor.BestinSensor(device, hub)
        for device in ctrl.devices.values()
        if device.domain == "sensor"
    }


KWH = sensor.UnitOfEnergy.KILO_WATT_HOUR
M3 = sensor.UnitOfVolume.CUBIC_METERS
M3H = sensor.UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR
WATT = sensor.UnitOfPower.WATT
CLS = sensor.SensorDeviceClass

# (value, unit, device class, state class), all as upstream 34df0cd reports them.
UPSTREAM = {
    "General": {
        "electric_total": (36151.6, KWH, CLS.ENERGY, "total_increasing"),
        "electric_realtime": (1222, WATT, CLS.POWER, "measurement"),
        "gas_total": (511.19, M3, CLS.GAS, "total_increasing"),
        "gas_realtime": (0.0, M3H, None, "measurement"),
        "heat_total": (36.61, M3, None, "total_increasing"),
        "heat_realtime": (0.0, M3H, None, "measurement"),
        "hotwater_total": (1004.24, M3, None, "total_increasing"),
        "hotwater_realtime": (0.0, M3H, None, "measurement"),
        "water_total": (480.53, M3, CLS.WATER, "total_increasing"),
        "water_realtime": (0.0, M3H, None, "measurement"),
    },
    "AIO": {
        "electric_total": (36151.6, KWH, CLS.ENERGY, "total_increasing"),
        "electric_realtime": (1222, WATT, CLS.POWER, "measurement"),
        "gas_total": (423.6, M3, CLS.GAS, "total_increasing"),
        "gas_realtime": (0.0, M3H, None, "measurement"),
        "water_total": (480.53, M3, CLS.WATER, "total_increasing"),
        "water_realtime": (0.0, M3H, None, "measurement"),
    },
}

for gateway, want in UPSTREAM.items():
    sensors = rs485_sensors(gateway)
    for meter, expected in want.items():
        entity = sensors[f"bestin_energy_{meter}"]
        check(
            f"{gateway} {meter}",
            (
                entity.native_value,
                entity.native_unit_of_measurement,
                entity.device_class,
                entity.state_class,
            ),
            expected,
        )

# v1.4.10 fixed these. Rebuilding their key from the device_id would give
# "1:mine:elec", so make sure the RS-485 fix did not undo that.
for device_type, device_id, unit, state_class in (
    ("energy:mineelec", "bestin_energy_1_mine_elec", KWH, "total_increasing"),
    ("energy:avggas", "bestin_energy_1_avg_gas", M3, "total"),
):
    info = types.SimpleNamespace(device_type=device_type, device_id=device_id, state=1.5)
    entity = sensor.BestinSensor(types.SimpleNamespace(info=info), None)
    check(
        f"iPark app {device_type} keeps its v1.4.10 fix",
        (entity.native_value, entity.native_unit_of_measurement, entity.state_class),
        (1.5, unit, state_class),
    )

# Thermostat step: only the iPark app server rounds to whole degrees.
for label, data, has_version, want in (
    ("iPark app", {iparkapp_const.CONF_IPARKAPP_SITE: "x"}, True, 1.0),
    ("cloud v1", {"username": "x"}, True, 0.5),
    ("cloud v2", {"session": {}}, True, 0.5),
    ("RS-485", {"port": 8899}, False, 0.5),
):
    hub = object.__new__(hub_module.BestinHub)
    hub.entry = types.SimpleNamespace(data=data)
    entity = object.__new__(climate.BestinClimate)
    entity.hub = hub
    entity._version_exists = has_version
    check(f"thermostat step on {label}", entity.target_temperature_step, want)


# A new RS-485 install has no saved gateway mode. Setup must finish.
class _Entries:
    async def async_forward_entry_setups(self, entry, platforms):
        self.forwarded = True


async def new_install():
    entry = types.SimpleNamespace(
        entry_id="e",
        unique_id="1.2.3.4",
        data={"host": "1.2.3.4", "port": 8899},
        options={},
        async_on_unload=lambda *a: None,
        add_update_listener=lambda *a: None,
    )
    hass = types.SimpleNamespace(
        data={},
        config_entries=_Entries(),
        bus=types.SimpleNamespace(async_listen_once=lambda *a: None),
    )

    async def connect(self):
        return True

    async def initialize(self):
        # What determine_gateway_mode leaves behind, without a serial bus.
        self.gateway_mode = ("General", None)

    hub_module.BestinHub.connect = connect
    hub_module.BestinHub.async_initialize_serial = initialize
    await integration.async_setup_entry(hass, entry)
    return hass


try:
    hass = asyncio.run(new_install())
    check("new RS-485 install finishes setup", hass.config_entries.forwarded, True)
    check("hub device gets the detected mode", _device_registry.models, ["General-generation"])
except Exception as ex:  # noqa: BLE001
    check("new RS-485 install finishes setup", repr(ex), None)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
