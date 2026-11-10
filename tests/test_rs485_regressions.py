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
    ATTR_HVAC_ACTION="hvac_action",
    HVACAction=types.SimpleNamespace(HEATING="heating", IDLE="idle", OFF="off"),
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

# Fixes found in laz-'s fork (github.com/laz-/ha-bestin).
CM = hub_module.ConnectionManager


class _Writer:
    def __init__(self):
        self.closed = False

    def is_closing(self):
        return self.closed

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


def _socket_cm(data=b"", eof=False):
    cm = CM("10.0.0.1:8899")
    cm.reader = asyncio.StreamReader()
    if data:
        cm.reader.feed_data(data)
    if eof:
        cm.reader.feed_eof()
    cm.writer = _Writer()
    cm.reconnects = 0

    async def fake_reconnect():
        cm.reconnects += 1
        await cm._close_writer()
        return False

    cm.reconnect = fake_reconnect
    return cm


async def connection_cases():
    # EOF used to return b'' forever with no reconnect.
    cm = _socket_cm(eof=True)
    got = await cm.receive()
    check("EOF reconnects", (got, cm.reconnects, cm.is_connected()), (None, 1, False))

    # A half-open socket used to block forever.
    cm = _socket_cm()
    cm.read_timeout = 0.05
    got = await cm.receive()
    check("silence times out and reconnects", (got, cm.reconnects), (None, 1))

    # A closed socket writer no longer counts as connected.
    cm = _socket_cm()
    cm.writer.closed = True
    check("closed writer is not connected", cm.is_connected(), False)

    # 0x32 (second gas valve) is a fixed 10-byte packet, not 0x80 = 128 bytes.
    gas2 = bytearray([0x02, 0x32, 0x80, 0x05, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00])
    therm = bytearray.fromhex("02281091000101170100f800000000ff")
    cm = _socket_cm(bytes(gas2) + bytes(therm))
    first = await cm.receive()
    second = await cm.receive()
    check("0x32 framed as 10 bytes", (len(first), first[1]), (10, 0x32))
    check("packet after 0x32 not swallowed", (len(second), second[1]), (16, 0x28))

    # Real gas valve packets captured by Kevrik (https://github.com/Kevrik/ha-bestin),
    # including the 02 31 01 / 02 31 81 kind that upstream framed wrongly.
    real_gas = [
        bytes.fromhex(h) for h in (
            "02310009000000000042",
            "02318009800000002062",
            "0231010A000000002062",
            "0231810A800000002062",
        )
    ]
    cm = _socket_cm(b"".join(real_gas) + bytes(therm))
    framed = [await cm.receive() for _ in range(len(real_gas) + 1)]
    check(
        "real gas packets framed one by one",
        [bytes(p) for p in framed[:-1]],
        real_gas,
    )
    check("packet after real gas packets not swallowed", (len(framed[-1]), framed[-1][1]), (16, 0x28))
    check(
        "real gas packets pass checksum",
        [controller.BestinController.verify_checksum(None, p) for p in real_gas],
        [True] * 4,
    )

    # Two tasks fail at once: the second must not close what the first reopened.
    cm = CM("10.0.0.1:8899")
    old = _Writer()
    cm.writer = old
    opened = []

    async def fake_connect(timeout=5):
        await asyncio.sleep(0.01)
        cm.writer = _Writer()
        opened.append(cm.writer)
        return True

    cm.connect = fake_connect
    cm.last_reconnect_attempt = None
    results = await asyncio.gather(cm.reconnect(), cm.reconnect())
    check(
        "concurrent reconnect opens once and keeps it",
        (results, len(opened), cm.writer is opened[0], cm.is_connected()),
        ([True, True], 1, True, True),
    )

    # A refused connection returns False instead of recursing into reconnect().
    cm = CM("10.0.0.1:8899")

    async def refuse():
        raise ConnectionRefusedError("refused")

    cm._connect_socket = refuse
    check("refused connect returns False", await cm.connect(), False)


asyncio.run(connection_cases())

ctrl = object.__new__(controller.BestinController)
ctrl.gateway_type = "General"
ctrl.hub_id = "hub"
ctrl.devices = {}
ctrl.entity_groups = {}
ctrl.timestamp = 0
ctrl.add_device_callback = lambda signal, device: None
for header, state in ((0x31, 1), (0x32, 0)):
    packet = bytearray([0x02, header, 0x80, 0x05, 0x00, state, 0x00, 0x00, 0x00, 0x00])
    packet[-1] = ctrl.calculate_checksum(packet)
    ctrl.handle_device_packet(packet)
check(
    "two gas valves become gas_0 and gas_1",
    {d: p.info.state for d, p in ctrl.devices.items() if "gas" in d},
    {"bestin_gas_0": True, "bestin_gas_1": False},
)
check("gas_0 command goes to 0x31", ctrl.make_gas_packet(1, 0, 0, None, False)[1], 0x31)
check("gas_1 command goes to 0x32", ctrl.make_gas_packet(1, 1, 0, None, False)[1], 0x32)

queue_item = {"command_packet": None}
ctrl.validate_response(bytearray(10), queue_item)
check("reply before any command is ignored", "acknowledgment" in queue_item, False)

check("unknown sub-type is skipped", ctrl.initial_device("light_1", "sparkle", 1), None)


async def climate_cases():
    sent = []
    entity = object.__new__(climate.BestinClimate)
    entity._version_exists = False
    entity._hvac_modes = ["off", "heat"]

    async def enqueue_command(**kwargs):
        sent.append(kwargs)

    entity.enqueue_command = enqueue_command
    await entity.async_turn_on()
    await entity.async_turn_off()
    check("thermostat turn on and off send commands", sent, [{"mode": True}, {"mode": False}])


asyncio.run(climate_cases())


async def stop_waits():
    ctrl2 = object.__new__(controller.BestinController)
    finished = []

    async def worker():
        try:
            await asyncio.sleep(10)
        finally:
            await asyncio.sleep(0)
            finished.append(True)

    ctrl2.tasks = [asyncio.get_running_loop().create_task(worker())]
    await asyncio.sleep(0)
    await ctrl2.stop()
    check("stop waits for tasks to end", finished, [True])


asyncio.run(stop_waits())


# Fixes found in pjb5592's fork.
class _FanFeature(enum.IntFlag):
    SET_SPEED = 1
    TURN_ON = 2
    TURN_OFF = 4
    PRESET_MODE = 8


sys.modules["homeassistant.components.fan"].FanEntity = _Entity
sys.modules["homeassistant.components.fan"].FanEntityFeature = _FanFeature
sys.modules["homeassistant.components.fan"].ATTR_PRESET_MODE = "preset_mode"
sys.modules["homeassistant.components.fan"].ATTR_PRESET_MODES = "preset_modes"
_module("homeassistant.util")
_module(
    "homeassistant.util.percentage",
    ordered_list_item_to_percentage=lambda items, item: (items.index(item) + 1) * 100 // len(items),
    percentage_to_ordered_list_item=lambda items, pct: items[0],
)
sys.modules["homeassistant.const"].STATE_ON = "on"
sys.modules["homeassistant.const"].STATE_OFF = "off"
fan = _load("fan")

for label, on_off, speed, want in (
    ("stopped (speed 0)", 0x00, 0x00, 0),
    ("speed 1", 0x01, 0x01, 33),
    ("speed 3", 0x01, 0x03, 100),
):
    packet = bytearray(10)
    packet[5], packet[6] = on_off, speed
    _, state = controller.BestinController.parse_fan(None, packet)
    entity = object.__new__(fan.BestinFan)
    entity._device_info = types.SimpleNamespace(state=state)
    entity._speed_list = state["speed_list"]
    check(f"local fan percentage when {label}", entity.percentage, want)

# Gen2 room 1 with two lights: the first dims, the second is on/off only.
packet = bytearray(18 + 13 * 2)
packet[1], packet[10], packet[11] = 0x31, 2, 0
packet[18], packet[19], packet[20] = 0x01, 50, 30
packet[31], packet[32], packet[33] = 0x01, 0, 0
state = controller.BestinController.parse_state_gen2(None, packet)
lights = state[1]["light"]
check(
    "Gen2 light without dimming is kept",
    sorted(k for k in lights if not k.startswith("dcvalue")),
    ["0", "1"],
)
check("Gen2 on/off light state", lights["1"]["state"], True)


async def missing_maker():
    ctrl3 = object.__new__(controller.BestinController)
    queue = {"device_type": "nosuch", "timestamp": 0, "room_id": 0,
             "pos_id": 0, "sub_type": None, "value": True}
    raised = None
    try:
        await ctrl3.send_packet_queue(queue)
    except Exception as ex:
        raised = type(ex).__name__
    check("missing packet maker is skipped without error", (raised, "command_packet" in queue), (None, False))


asyncio.run(missing_maker())

# Thermostat heating or idle (status bits from Camblin, https://github.com/Camblin/ha-bestin).
# Byte 6: 0x01 on, 0x10 heating now. The real dump packet has 0x02 (off).
def therm_action(byte6):
    pkt = bytearray.fromhex("02281091750202190109002173008019")
    pkt[6] = byte6
    room, state = controller.BestinController.parse_thermostat(None, pkt)
    return state["hvac_mode"], state["hvac_action"]

check("thermostat off from real packet", therm_action(0x02), ("off", "off"))
check("thermostat on and heating", therm_action(0x11), ("heat", "heating"))
check("thermostat on and idle", therm_action(0x01), ("heat", "idle"))
check("heating bit ignored when off", therm_action(0x12), ("off", "off"))

ent = object.__new__(climate.BestinClimate)
ent._device_info = types.SimpleNamespace(state={"hvac_mode": "heat"})
check("no hvac_action on gateways that do not report it", ent.hvac_action, None)
ent._device_info.state["hvac_action"] = "heating"
check("hvac_action read from state", ent.hvac_action, "heating")

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
