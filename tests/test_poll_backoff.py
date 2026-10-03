"""Offline tests for the v1.4.12 absent-device-class polling backoff.

A one-per-home class the wallpad doesn't serve (gas, on this install) answered
``result="fail"`` on every 30 s poll forever — ~2,800 wasted requests a day.
Backing off is easy; backing off *recoverably* is the point of these tests:
a class that merely has a bad run at startup (the doorlock fails
intermittently) must not be written off permanently.

Loads the real iparkapp.py with stubbed Home Assistant / aiohttp modules.
"""

import asyncio
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
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.climate",
    "homeassistant.components.climate.const",
    "homeassistant.components.fan",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.event",
):
    _fake(_name)

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
for _name in ("bst.const", "bst.duty_cycle"):
    _fake(_name)
sys.modules["bst.const"].LOGGER = logging.getLogger("test")

# iparkapp_const is pure stdlib — load the real thing so RESULT_OK /
# RESULT_ERRORS_FATAL compare correctly.
_spec = importlib.util.spec_from_file_location(
    "bst.iparkapp_const", f"{REPO}/iparkapp_const.py"
)
ipc = importlib.util.module_from_spec(_spec)
sys.modules["bst.iparkapp_const"] = ipc
_spec.loader.exec_module(ipc)

spec = importlib.util.spec_from_file_location("bst.iparkapp", f"{REPO}/iparkapp.py")
ip = importlib.util.module_from_spec(spec)
sys.modules["bst.iparkapp"] = ip
spec.loader.exec_module(ip)

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


FAIL_BODY = (
    '<imap ver="1.0"><service type="reply" result="fail"/></imap>'
)
OK_BODY = (
    '<imap ver="1.0"><service type="reply" result="ok"/></imap>'
)


def make_api(bodies):
    """Build an API instance without __init__, with a scripted _request."""
    api = ip.BestinIparkAppAPI.__new__(ip.BestinIparkAppAPI)
    api._poll_cycle = 0
    api._class_fatal_streak = {}
    api._class_ever_ok = set()
    api._class_next_probe = {}
    api._class_backed_off = set()
    api._room_exists = {}
    api._unit_cnt = {}
    api.requests = []

    async def _request(path, params, *, referer_path="/", quiet=False):
        api.requests.append(params.get("req_name"))
        return bodies.pop(0) if bodies else FAIL_BODY

    api._request = _request
    return api


GAS = ipc.DEVICE_CLASSES["gas"]


def poll(api, cls, n):
    """Simulate n poll cycles, honouring the backoff gate in _poll_all."""
    polled = 0
    for _ in range(n):
        api._poll_cycle += 1
        if api._poll_cycle < api._class_next_probe.get(cls.key, 0):
            continue
        polled += 1
        asyncio.run(api._fetch_class(cls))
    return polled


# --- a class that never works gets backed off, but not switched off ---------
api = make_api([])                       # always fails
polled = poll(api, GAS, 10)
check("backs off after threshold", polled, ip.ABSENT_CLASS_THRESHOLD)
check("  ...backoff recorded", "gas" in api._class_backed_off, True)
check(
    "  ...next probe scheduled",
    api._class_next_probe["gas"] > api._poll_cycle,
    True,
)

# It must come back on its own — this is the whole point.
polled_later = poll(api, GAS, ip.ABSENT_CLASS_RETRY_CYCLES + 2)
check("re-probes itself without a reload", polled_later >= 1, True)

# Rate really is reduced: over a long run it polls ~once per retry window
# instead of every cycle.
api2 = make_api([])
total = poll(api2, GAS, 1000)
check(
    "long run stays sparse (<40 polls in 1000 cycles)",
    total < 40,
    True,
)
check("  ...and is not zero", total > 0, True)


# --- the doorlock scenario the backoff must survive -------------------------
# Unlucky startup: the first ABSENT_CLASS_THRESHOLD polls fail, then the
# device answers. It must resume full-rate polling, not stay dark.
bodies = [FAIL_BODY] * ip.ABSENT_CLASS_THRESHOLD + [OK_BODY] * 5
api3 = make_api(bodies)
poll(api3, GAS, ip.ABSENT_CLASS_THRESHOLD)
check("unlucky start -> backed off", "gas" in api3._class_backed_off, True)

# Advance to the re-probe; that poll succeeds.
poll(api3, GAS, ip.ABSENT_CLASS_RETRY_CYCLES + 1)
check("recovers after one good reply", "gas" in api3._class_backed_off, False)
check("  ...backoff cleared", api3._class_next_probe.get("gas"), None)
check("  ...streak reset", api3._class_fatal_streak.get("gas"), None)
check("  ...marked as seen-OK", "gas" in api3._class_ever_ok, True)

# And from then on it polls every cycle again.
before = len(api3.requests)
poll(api3, GAS, 5)
check("full-rate polling resumes", len(api3.requests) - before, 5)


# --- a class that has ever worked is never backed off ------------------------
api4 = make_api([OK_BODY] + [FAIL_BODY] * 50)
poll(api4, GAS, 40)
check("intermittent failures never back off a known-good class",
      "gas" in api4._class_backed_off, False)
check("  ...still polled every cycle", len(api4.requests), 40)

# --- v1.4.15: a missing room that answers "fail" is backed off too ----------
LIGHT = ipc.DEVICE_CLASSES["light"]


def poll_room(api, cls, room, n):
    """Simulate n poll cycles for one room, honouring the per-room gate."""
    polled = 0
    for _ in range(n):
        api._poll_cycle += 1
        if not api._room_exists.get((cls.key, room), True):
            continue
        if api._poll_cycle < api._class_next_probe.get((cls.key, room), 0):
            continue
        polled += 1
        asyncio.run(api._fetch_class(cls, room=room))
    return polled


api5 = make_api([])
polled = poll_room(api5, LIGHT, 3, 10)
check("missing room backs off after threshold", polled, ip.ABSENT_CLASS_THRESHOLD)
check("  ...keyed per room", (LIGHT.key, 3) in api5._class_backed_off, True)
check("  ...class itself untouched", LIGHT.key in api5._class_backed_off, False)
check("  ...room re-probes itself",
      poll_room(api5, LIGHT, 3, ip.ABSENT_CLASS_RETRY_CYCLES + 2) >= 1, True)

api6 = make_api([OK_BODY] + [FAIL_BODY] * 50)
poll_room(api6, LIGHT, 1, 20)
check("a room that has worked is never backed off",
      (LIGHT.key, 1) in api6._class_backed_off, False)

# --- v1.4.17: one empty reply at startup must not drop a real room ----------
TEMPER = ipc.DEVICE_CLASSES["temper"]
api6b = make_api([""] + [OK_BODY] * 5)
polled = poll_room(api6b, TEMPER, 3, 3)
check("empty first reply: room still polled", polled, 3)
check("  ...not marked absent", api6b._room_exists.get((TEMPER.key, 3)), True)

api6c = make_api([""] * 50)
polled = poll_room(api6c, TEMPER, 3, 10)
check("always-empty room backs off like 'fail'", polled, ip.ABSENT_CLASS_THRESHOLD)
check("  ...and re-probes itself",
      poll_room(api6c, TEMPER, 3, ip.ABSENT_CLASS_RETRY_CYCLES + 2) >= 1, True)


# --- v1.4.15: thermostats are polled every THERMOSTAT_POLL_SECONDS ----------
class _Duty:
    def __init__(self, active):
        self.active = active

    def any_active(self):
        return self.active


class _Dev:
    def __init__(self, state):
        self.info = types.SimpleNamespace(state=state)


def thermo_api(duty_active=False, room_mode="off", answers=True):
    api = make_api([])
    api._temper_next_poll = 0.0
    api.duty_cycle = _Duty(duty_active)
    api.devices = {"bestin_temper_1": _Dev({"raw_mode": room_mode})}
    api.calls = []

    async def _fake_fetch(cls, room=None):
        api.calls.append(cls.key)
        if answers and room is not None:
            api._class_ever_ok.add((cls.key, room))

    api._fetch_class = _fake_fetch
    return api


clock = [1000.0]
ip.time.monotonic = lambda: clock[0]
ROOMS = len(ipc.ROOM_PROBE_RANGE)


def run_polls(api, n, between=None):
    for i in range(n):                   # polls 60 s apart
        asyncio.run(api._poll_all())
        if between:
            between(i)
        clock[0] += 60
    return api.calls.count("temper") // ROOMS


api7 = thermo_api(room_mode="on")
check("heating: thermostats polled twice in 9 minutes", run_polls(api7, 10), 2)
check("other classes polled every time", api7.calls.count("ventil"), 10)

api8 = thermo_api()
check("all off: thermostats polled 3 times in 69 minutes", run_polls(api8, 70), 3)

api9 = thermo_api(duty_active=True)
check("duty-cycled room counts as heating", run_polls(api9, 10), 2)

api10 = thermo_api()
check("HA command wakes the 5 minute poll",
      run_polls(api10, 10, lambda i: i == 0 and api10._wake_thermostat_poll()), 2)


# --- v1.4.19: a failed first thermostat poll is retried on the next poll ---
api11 = thermo_api(answers=False)
check("no room answered yet: thermostats asked every poll", run_polls(api11, 3), 3)
api12 = thermo_api(answers=False)
run_polls(api12, 1)
api12._class_ever_ok.update(("temper", n) for n in ipc.ROOM_PROBE_RANGE if n != 2)
check("one room still silent: thermostats asked every poll",
      run_polls(api12, 4) - 1, 4)
api12._class_ever_ok.add(("temper", 2))
check("  ...back to the 30 minute idle poll once every room answers",
      run_polls(api12, 10) - 5, 1)
api13 = thermo_api()
api13._class_ever_ok.discard(("temper", 2))
api13._room_exists[("temper", 2)] = False
run_polls(api13, 10)
check("  ...a room known to be absent does not hold the retry",
      api13.calls.count("temper"), ROOMS - 1)
api14 = thermo_api(answers=False)
run_polls(api14, 1)
api14._class_ever_ok.update(("temper", n) for n in ipc.ROOM_PROBE_RANGE if n != 2)
api14._class_next_probe[("temper", 2)] = 10**6
run_polls(api14, 10)
check("  ...nor does a backed-off room",
      api14.calls.count("temper"), ROOMS + ROOMS - 1)


# --- v1.4.17: never more than MAX_CONCURRENT_REQUESTS in flight -------------
class _Resp:
    def __init__(self, track):
        self.track = track

    async def __aenter__(self):
        self.track["now"] += 1
        self.track["peak"] = max(self.track["peak"], self.track["now"])
        # sleep(0) only yields; a timed sleep would hang on the fake clock
        # patched in above.
        for _ in range(5):
            await asyncio.sleep(0)
        return self

    async def __aexit__(self, *exc):
        self.track["now"] -= 1

    def raise_for_status(self):
        pass

    async def text(self):
        return OK_BODY


class _Session:
    def __init__(self, track):
        self.track = track

    def get(self, url, **kw):
        return _Resp(self.track)


async def _burst():
    track = {"now": 0, "peak": 0}
    api = ip.BestinIparkAppAPI.__new__(ip.BestinIparkAppAPI)
    api.host = "example.invalid"
    api.session = _Session(track)
    api._request_slots = asyncio.Semaphore(ip.MAX_CONCURRENT_REQUESTS)
    bodies = await asyncio.gather(*(api._request("/x", {}) for _ in range(28)))
    return track["peak"], bodies.count(OK_BODY)


peak, done = asyncio.run(_burst())
check("28 requests at once: peak in flight", peak, ip.MAX_CONCURRENT_REQUESTS)
check("  ...all 28 still answered", done, 28)


# --- v1.4.19: a total timeout is caught and logged, not lost --------------
class _TimeoutSession:
    def get(self, url, **kw):
        raise asyncio.TimeoutError()


async def _timed_out():
    api = ip.BestinIparkAppAPI.__new__(ip.BestinIparkAppAPI)
    api.host = "example.invalid"
    api.session = _TimeoutSession()
    api._request_slots = asyncio.Semaphore(ip.MAX_CONCURRENT_REQUESTS)
    return await api._request("/x", {})


ip.aiohttp.ClientError = type("ClientError", (Exception,), {})
check("timeout returns None instead of raising", asyncio.run(_timed_out()), None)


# --- v1.4.19: a device that never answered fails quietly -------------------
class _Levels:
    def __init__(self):
        self.seen = []

    def __getattr__(self, level):
        return lambda *a, **k: self.seen.append(level)


async def _fetch_timed_out(ever_ok):
    api = make_api([])
    api.host = "example.invalid"
    api.session = _TimeoutSession()
    api._request_slots = asyncio.Semaphore(ip.MAX_CONCURRENT_REQUESTS)
    api._request = types.MethodType(ip.BestinIparkAppAPI._request, api)
    if ever_ok:
        api._class_ever_ok.add("gas")
    await api._fetch_class(ipc.DEVICE_CLASSES["gas"])


real_logger, ip.LOGGER = ip.LOGGER, _Levels()
asyncio.run(_fetch_timed_out(ever_ok=False))
check("never-answered device: timeout logged at debug only",
      "warning" in ip.LOGGER.seen, False)
ip.LOGGER = _Levels()
asyncio.run(_fetch_timed_out(ever_ok=True))
check("  ...a device that has answered before still warns",
      "warning" in ip.LOGGER.seen, True)
ip.LOGGER = real_logger


# --- v1.4.19: devices found before the platforms load still get entities ---
api13 = ip.BestinIparkAppAPI.__new__(ip.BestinIparkAppAPI)
api13.devices = {
    "bestin_temper_1": types.SimpleNamespace(domain="climate"),
    "bestin_temper_2": types.SimpleNamespace(domain="climate"),
    "bestin_livinglight_2": types.SimpleNamespace(domain="light"),
}
api13.entity_groups = {"climate": set()}     # what climate.py's setup leaves
check("platform setup sees thermostats polled before it loaded",
      len(api13.get_devices_from_domain("climate")), 2)
check("  ...and only its own domain",
      len(api13.get_devices_from_domain("light")), 1)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
