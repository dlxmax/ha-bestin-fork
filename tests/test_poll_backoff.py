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

    async def _request(path, params, *, referer_path="/"):
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

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
