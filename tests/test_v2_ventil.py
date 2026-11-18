"""Offline tests for issue #13: Smart Home 2.0 ventilation speed.

The official app (iPark Smart Home 2.0 1.5.4, ventil page) sends on/off and
speed the same way:
    PUT /v2/api/features/ventil/{seq}/apply
    {"unit": <unit name from the status reply>, "state": on|off|low|mid|high, "mode": ""}
It shows a reported "on" as low and "unknown" as off.

Uses the real aiohttp against a local test server, with Home Assistant
stubbed. Run with: uv run --with aiohttp python tests/test_v2_ventil.py
"""

import asyncio
import enum
import importlib.util
import logging
import os
import sys
import types

from aiohttp import web

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

    def __iter__(self):
        return iter(())


def _fake(name):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda attr: _Permissive()
    sys.modules[name] = mod
    return mod


for _name in (
    "xmltodict",
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
):
    _fake(_name)

ha_const = sys.modules["homeassistant.const"]
for _key in ("CONF_IP_ADDRESS", "CONF_USERNAME", "CONF_PASSWORD", "CONF_UUID",
             "CONF_SCAN_INTERVAL", "CONF_URL"):
    setattr(ha_const, _key, _key.lower().removeprefix("conf_"))
sys.modules["homeassistant.core"].callback = lambda func: func

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
for _name in ("bst.const", "bst.controller", "bst.until"):
    _fake(_name)
sys.modules["bst.const"].LOGGER = logging.getLogger("test")
sys.modules["bst.const"].CONF_SESSION = "session"
sys.modules["bst.const"].BRAND_PREFIX = "bestin"
sys.modules["bst.const"].V2_USER_AGENT = "Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36"


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, f"{REPO}/{filename}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod



failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got {got!r}, want {want!r}")
    if not ok:
        failures.append(name)


for _key, _val in (("ATTR_STATE", "state"), ("WIND_SPEED", "wind_speed")):
    setattr(ha_const, _key, _val)
sys.modules["homeassistant.components.climate.const"].ATTR_PRESET_MODE = "preset_mode"
for _key, _val in (("SPEED_STR_LOW", "low"), ("SPEED_STR_MEDIUM", "mid"),
                   ("SPEED_STR_HIGH", "high")):
    setattr(sys.modules["bst.const"], _key, _val)
center = _load("bst.center", "center.py")

puts: list[dict] = []
status = {"unit": "ventil", "state": "off"}


async def ventil_handler(request):
    if request.method == "PUT":
        puts.append(await request.json())
        status["state"] = puts[-1]["state"]
    unit = {"unit": status["unit"], "state": status["state"], "mode": "", "unit_mode": ""}
    return web.json_response({"result": "ok", "units": [unit]})


async def main():
    app = web.Application()
    app.router.add_route("*", "/v2/api/features/ventil/1/apply", ventil_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    class Entry:
        data = {"uuid": "UUID", "ip_address": "addr",
                "session": {"url": f"http://127.0.0.1:{port}", "access-token": "TOKEN"}}
        options = {}

    class Hass:
        def create_task(self, coro):
            return asyncio.ensure_future(coro)

    api = center.BestinCenterAPI(Hass(), Entry(), {}, "hub", "Smart Home 2.0", lambda *a: None)
    api.result_after_request = lambda resp: resp.get("result")
    seen_state: list = []
    api.set_device = lambda kind, num, unit, state: seen_state.append((kind, num, state))

    async def send(value, **kwargs):
        puts.clear()
        seen_state.clear()
        await api.enqueue_command("bestin_ventil_1", value, **kwargs)
        return puts[-1] if puts else None

    # What fan.py sends: turn_on/off positionally, speed as set_percentage=.
    check("turn on = app body", await send("on"),
          {"unit": "ventil", "state": "on", "mode": ""})
    check("speed high = app body (was unit 'set_percentage')",
          await send(None, set_percentage="high"),
          {"unit": "ventil", "state": "high", "mode": ""})
    check("speed read back as high", seen_state[-1][2]["wind_speed"], "high")
    check("speed mid", (await send(None, set_percentage="mid"))["state"], "mid")
    check("turn off", await send("off"), {"unit": "ventil", "state": "off", "mode": ""})
    check("off read back", (seen_state[-1][2]["state"], seen_state[-1][2]["wind_speed"]),
          (False, "off"))

    # The app sends back whatever unit name the status reply used.
    status["unit"] = "ventil1"
    await api.fetch_feature_status("ventil", 1)
    check("status unit name echoed back",
          (await send(None, set_percentage="low"))["unit"], "ventil1")

    # Reported states the app maps on the v2 route: "on" shows as low,
    # "unknown" as off.
    status["unit"] = "ventil"
    for reported, want in (("on", (True, "low")), ("unknown", (False, "off")),
                           ("high", (True, "high"))):
        status["state"] = reported
        seen_state.clear()
        await api.fetch_feature_status("ventil", 1)
        got = seen_state[-1][2]
        check(f"v2 reported {reported!r}", (got["state"], got["wind_speed"]), want)

    # The shared parser (also used by Smart Home 1.0) is unchanged.
    seen_state.clear()
    api._parse_ventil_status(1, "1", "on")
    check("v1 parser untouched", seen_state[-1][2]["wind_speed"], "on")

    await api.session.close()
    await runner.cleanup()


asyncio.run(main())


class _FanFeature(enum.IntFlag):
    SET_SPEED = 1
    TURN_ON = 2
    TURN_OFF = 4
    PRESET_MODE = 8


class _Device:
    def __init__(self, device, hub):
        self._device_info = device


_fan_ha = sys.modules["homeassistant.components.fan"] = types.ModuleType("homeassistant.components.fan")
_fan_ha.DOMAIN, _fan_ha.FanEntity, _fan_ha.FanEntityFeature = "fan", object, _FanFeature
_fan_ha.ATTR_PRESET_MODE, _fan_ha.ATTR_PRESET_MODES = "preset_mode", "preset_modes"
for _name in ("homeassistant.helpers.dispatcher", "homeassistant.helpers.entity_platform",
              "homeassistant.util", "homeassistant.util.percentage", "bst.hub"):
    _fake(_name)
sys.modules["homeassistant.util.percentage"].percentage_to_ordered_list_item = (
    lambda items, pct: items[max(0, -(-pct * len(items) // 100) - 1)])
sys.modules["bst.device"] = types.SimpleNamespace(BestinDevice=_Device)
ha_const.STATE_ON, ha_const.STATE_OFF = "on", "off"
for _key, _val in (("CONF_VERSION", "version"), ("SMART_HOME_2", "Smart Home 2.0"),
                   ("NEW_FAN", "new_fan"), ("PRESET_NV", "nv")):
    setattr(sys.modules["bst.const"], _key, _val)
fan = _load("bst.fan", "fan.py")


async def fan_turn_on(version):
    sent = []
    device = types.SimpleNamespace(
        state={"state": False, "wind_speed": "off", "speed_list": ["low", "mid", "high"]})
    api = types.SimpleNamespace(version=version) if version else types.SimpleNamespace()
    entity = fan.BestinFan(device, types.SimpleNamespace(api=api))

    async def set_pct(pct):
        sent.append(("set_percentage", pct))

    async def enqueue(data=None, **kw):
        sent.append(("enqueue", data))

    entity.async_set_percentage = set_pct
    entity.enqueue_command = enqueue
    await entity.async_turn_on(percentage=100)
    await entity.async_turn_on()
    return sent


async def fan_low_from_off(version):
    sent = []
    device = types.SimpleNamespace(
        state={"state": False, "wind_speed": "off", "speed_list": ["low", "mid", "high"]})
    api = types.SimpleNamespace(version=version) if version else types.SimpleNamespace()
    entity = fan.BestinFan(device, types.SimpleNamespace(api=api))

    async def enqueue(data=None, **kw):
        sent.append((data, kw))

    entity.enqueue_command = enqueue
    await entity.async_set_percentage(33)
    return sent


# The app sends "low" to an off fan; other gateways keep sending "on".
check("v2 33% from off sends low", asyncio.run(fan_low_from_off("Smart Home 2.0")),
      [(None, {"set_percentage": "low"})])
check("v1 33% from off unchanged", asyncio.run(fan_low_from_off("Smart Home 1.0")),
      [("on", {})])
check("RS-485 33% from off unchanged", asyncio.run(fan_low_from_off(None)),
      [("on", {})])
check("v2 turn_on honours percentage", asyncio.run(fan_turn_on("Smart Home 2.0")),
      [("set_percentage", 100), ("enqueue", "on")])
check("v1 turn_on unchanged", asyncio.run(fan_turn_on("Smart Home 1.0")),
      [("enqueue", "on"), ("enqueue", "on")])
check("RS-485 turn_on unchanged", asyncio.run(fan_turn_on(None)),
      [("enqueue", True), ("enqueue", True)])
print("\nall passed" if not failures else f"\nFAILURES: {failures}")
sys.exit(1 if failures else 0)
