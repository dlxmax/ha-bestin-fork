"""Offline tests for v1.4.23: two-elevator floors (issue #2) and the
config-flow hub with no entry yet (issue #4).

Loads the real center.py and hub.py with stubbed Home Assistant / aiohttp
modules, the same way test_center_session.py does.
"""

import asyncio
import json
import importlib.util
import logging
import os
import sys
import types

REPO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "custom_components",
    "bestin",
)


class _Permissive:
    def __getattr__(self, name):
        return _Permissive()

    def __call__(self, *a, **kw):
        return _Permissive()

    def __hash__(self):
        return 0

    def __eq__(self, other):
        return isinstance(other, _Permissive)

    def __iter__(self):
        return iter(())


def _fake(name):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda attr: _Permissive()
    sys.modules[name] = mod
    return mod


for _name in (
    "aiohttp",
    "xmltodict",
    "serial_asyncio_fast",
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.climate",
    "homeassistant.components.climate.const",
    "homeassistant.components.light",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.event",
    "homeassistant.helpers.dispatcher",
):
    _fake(_name)

sessions = []


class _FakeSession:
    def __init__(self, *a, **kw):
        self.closed = False
        self.close_calls = 0
        sessions.append(self)

    async def close(self):
        self.close_calls += 1
        self.closed = True


sys.modules["aiohttp"].ClientSession = _FakeSession
# @callback must stay identity, otherwise the decorated coroutines vanish.
sys.modules["homeassistant.core"].callback = lambda func: func

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
for _name in ("bst.const", "bst.controller", "bst.iparkapp", "bst.iparkapp_const", "bst.until"):
    _fake(_name)
sys.modules["bst.const"].LOGGER = logging.getLogger("test")


class BestinIparkAppError(Exception):
    pass


class IparkAppConnectionError(BestinIparkAppError):
    pass


errors_stub = types.ModuleType("bst.errors")
errors_stub.BestinIparkAppError = BestinIparkAppError
errors_stub.IparkAppConnectionError = IparkAppConnectionError
sys.modules["bst.errors"] = errors_stub


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, f"{REPO}/{filename}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


center = _load("bst.center", "center.py")
hub = _load("bst.hub", "hub.py")

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got {got!r}, want {want!r}")
    if not ok:
        failures.append(name)



class _Entry:
    data = {}
    options = {}


def make_api(cars=2):
    api = center.BestinCenterAPI(
        _Permissive(), _Entry(), {}, "hub", "Smart Home 2.0", lambda *a: None
    )
    api.elevator_number = cars
    api.register_elevator = "HOME"
    api.sets = {}

    def set_device(device_type, room, sub, value):
        api.sets[sub] = value

    api.set_device = set_device
    return api


def move(serial, floor, direction="down"):
    return json.dumps(
        {"address": "HOME", "move_info": {"Serial": serial, "Floor": floor, "MoveDir": direction}}
    )


async def no_sleep(_seconds):
    return None


async def test_two_cars():
    api = make_api(2)
    await api.handle_message_info(move("E2", "12"))
    await api.handle_message_info(move("E1", "3", "up"))
    await api.handle_message_info(move("E2", "11"))
    check("car seen first owns slot 1", api.sets.get("floor_1"), "11")
    check("second car gets slot 2", api.sets.get("floor_2"), "3")
    check("second car direction", api.sets.get("direction_2"), "Up")
    check("slots are stable", api.elevator_slots, {"E2": 1, "E1": 2})

    # Arrival: both cars show their own last floor, never 'Unknown'.
    shown = []
    real_set = api.set_device

    def record(device_type, room, sub, value):
        shown.append((sub, value))
        real_set(device_type, room, sub, value)

    api.set_device = record
    real_sleep = center.asyncio.sleep
    center.asyncio.sleep = no_sleep
    try:
        await api.handle_message_info(json.dumps({"address": "HOME", "arrived": True}))
    finally:
        center.asyncio.sleep = real_sleep
    check("arrival shows car 1 floor", ("floor_1", "11") in shown, True)
    check("arrival shows car 2 floor", ("floor_2", "3") in shown, True)
    check("no Unknown anywhere", any(v == "Unknown" for _, v in shown), False)
    check("then resets to idle", api.sets.get("direction_2"), "Idle")
    check("arrival flag set", api.elevator_arrived, True)


async def test_extra_car_ignored():
    api = make_api(1)
    await api.handle_message_info(move("A", "5"))
    await api.handle_message_info(move("B", "9"))
    check("only the configured number of slots", api.elevator_slots, {"A": 1})
    check("extra car does not overwrite slot 1", api.sets.get("floor_1"), "5")


def test_snapshot_drops_address():
    api = make_api(2)
    api._note_elevator_message({"address": "HOME", "move_info": {"Serial": "A"}})
    api._note_elevator_message({"address": "OTHER", "x": 1})
    snap = api.diagnostics_snapshot()
    check("snapshot kind", snap["kind"], "center")
    check("address not kept", any("address" in m for m in snap["elevator_messages"]), False)
    check("address match recorded", [m["address_matches"] for m in snap["elevator_messages"]], [True, False])
    json.dumps(snap)


def test_hub_without_entry():
    h = hub.BestinHub(_Permissive(), None)
    check("no entry -> no saved gateway mode (issue #4)", h.gateway_mode, None)
    check("conn_str uses the typed host and port", h.conn_str("10.0.0.5", 8899), "10.0.0.5:8899")


asyncio.run(test_two_cars())
asyncio.run(test_extra_car_ignored())
test_snapshot_drops_address()
test_hub_without_entry()

if failures:
    print("\nFAILURES:", failures)
    sys.exit(1)
print("\nall passed")
