"""Offline tests for the v1.4.14 "no reading published" handling.

2026-08-25: ``getEnergyAvr_monthly_*.php`` started answering with all three
requested months set to ``"0"`` for every category — the complex's metering
backend had stopped publishing. Verified live against the real server:

  [{"name":"전체 평균 사용량","data":["0","0","0"],"xaxis":[...]},
   {"name":"나의 세대 사용량","data":["0","0","0"],"xaxis":[...]}]

Through v1.4.13 that was recorded verbatim, so every energy sensor read a
hard 0. These tests pin the replacement rule: an all-zero series means "no
reading" (None → Unknown in HA), while a zero newest month behind real
earlier months is a normal start-of-billing-period 0 and passes through.

Loads the real iparkapp.py with stubbed Home Assistant / aiohttp modules.
"""

import asyncio
import importlib.util
import json
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


# --- latest_energy_reading -------------------------------------------------
latest = ip.latest_energy_reading

check("outage: every month zero -> no reading", latest(["0", "0", "0"]), None)
check("outage: numeric zeros too", latest([0, 0.0, 0]), None)
check("outage: blank strings -> no reading", latest(["", "", ""]), None)
check("normal: latest month wins", latest(["10", "20", "30.5"]), 30.5)
check(
    "start of month: real history, zero so far -> a real 0",
    latest(["120", "98", "0"]),
    0.0,
)
check("unparseable newest month -> no reading", latest(["120", "98", "n/a"]), None)
check("single-month series", latest(["7"]), 7.0)


# --- _fetch_energy end to end ----------------------------------------------
def make_api(body):
    api = ip.BestinIparkAppAPI.__new__(ip.BestinIparkAppAPI)
    api.set_calls = []

    async def _request(path, params, *, referer_path="/"):
        return body

    def _set_device(device_type, number, sub_id, status):
        api.set_calls.append((sub_id, status))

    api._request = _request
    api._set_device = _set_device
    return api


# The exact shape the live server returned on 2026-08-25.
OUTAGE_BODY = json.dumps([
    {"name": "전체 평균 사용량", "data": ["0", "0", "0"],
     "xaxis": ["2026-06", "2026-07", "2026-08"]},
    {"name": "나의 세대 사용량", "data": ["0", "0", "0"],
     "xaxis": ["2026-06", "2026-07", "2026-08"]},
], ensure_ascii=False)

GOOD_BODY = json.dumps([
    {"name": "전체 평균 사용량", "data": ["310", "295", "180"],
     "xaxis": ["2026-06", "2026-07", "2026-08"]},
    {"name": "나의 세대 사용량", "data": ["262", "248", "151.5"],
     "xaxis": ["2026-06", "2026-07", "2026-08"]},
], ensure_ascii=False)

api = make_api(OUTAGE_BODY)
asyncio.run(api._fetch_energy("Elec"))
check(
    "outage payload publishes Unknown, not 0",
    sorted(api.set_calls),
    [("avg_elec", None), ("mine_elec", None)],
)

api = make_api(GOOD_BODY)
asyncio.run(api._fetch_energy("Elec"))
check(
    "healthy payload still publishes the newest month",
    sorted(api.set_calls),
    [("avg_elec", 180.0), ("mine_elec", 151.5)],
)

# A non-JSON body (maintenance page) must not raise or publish anything.
api = make_api("<html>maintenance</html>")
asyncio.run(api._fetch_energy("Gas"))
check("non-JSON body publishes nothing", api.set_calls, [])

api = make_api(None)
asyncio.run(api._fetch_energy("Gas"))
check("failed request publishes nothing", api.set_calls, [])

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
