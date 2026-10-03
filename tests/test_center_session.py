"""Offline tests for v1.4.19 wallpad server session cleanup.

The wallpad server API (center.py) opened an aiohttp session in its
constructor and never closed it, so every reload of the integration left one
open and HA logged "Unclosed client session". These tests check that:

  1. stop() closes the session, and a second stop() is harmless,
  2. a failed start closes the session before the API is dropped.

Loads the real center.py and hub.py with stubbed Home Assistant / aiohttp
packages, the same way test_outage_retry.py does.
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


def make_api():
    return center.BestinCenterAPI(
        _Permissive(), _Entry(), {}, "hub", "Smart Home 2.0", lambda *a: None
    )


async def test_stop_closes_session():
    api = make_api()
    await api.stop()
    check("stop closes the session", api.session.closed, True)
    await api.stop()
    check("second stop does not close again", api.session.close_calls, 1)


async def test_failed_start_closes_session():
    sessions.clear()

    async def failing_start(self):
        raise OSError("wallpad server unreachable")

    center.BestinCenterAPI.start, real_start = failing_start, center.BestinCenterAPI.start
    try:
        owner = types.SimpleNamespace(
            hass=_Permissive(),
            entry=_Entry(),
            entity_groups={},
            hub_id="hub",
            cntr_version="Smart Home 2.0",
            async_add_device_callback=lambda *a: None,
            api=None,
        )
        owner._async_discard_api = types.MethodType(hub.BestinHub._async_discard_api, owner)
        raised = None
        try:
            await hub.BestinHub.async_initialize_center(owner)
        except RuntimeError as ex:
            raised = ex
    finally:
        center.BestinCenterAPI.start = real_start
    check("failed start still raises", raised is not None, True)
    check("failed start drops the API", owner.api, None)
    check("failed start closes the session", [s.closed for s in sessions], [True])


async def main():
    await test_stop_closes_session()
    await test_failed_start_closes_session()


asyncio.run(main())
print("FAILURES:", failures or "none")
sys.exit(1 if failures else 0)
