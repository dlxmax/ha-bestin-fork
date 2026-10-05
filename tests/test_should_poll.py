"""Offline test for v1.4.21: HA must not poll BESTIN entities itself.

Every entity gets its state pushed through ``update_callbacks`` and has no
``async_update``, so HA's own 30 s refresh (``should_poll`` was True in iPark
app mode through v1.4.20) did nothing except rewrite identical state.

Loads the real device.py with stubbed Home Assistant modules.
"""

import importlib.util
import os
import sys
import types

REPO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "custom_components",
    "bestin",
)


def _module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


class _DeviceInfo:
    __annotations__ = {}


class _Entity:
    pass


_module("homeassistant")
_module("homeassistant.helpers")
_module("homeassistant.helpers.device_registry", DeviceInfo=_DeviceInfo)
_module("homeassistant.helpers.entity", Entity=_Entity)
_module("homeassistant.core", callback=lambda f: f)

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
_module("bst.const", DOMAIN="bestin", FRIENDLY_TYPE_NAMES={}, MAIN_DEVICES=())
_module("bst.until", formatted_name=lambda s: s)

_spec = importlib.util.spec_from_file_location("bst.device", f"{REPO}/device.py")
device = importlib.util.module_from_spec(_spec)
sys.modules["bst.device"] = device
_spec.loader.exec_module(device)

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


class _Hub:
    def __init__(self, polling):
        self.is_polling = polling


for polling in (True, False):
    entity = object.__new__(device.BestinDevice)
    entity.hub = _Hub(polling)
    check(f"should_poll is False when hub.is_polling={polling}", entity.should_poll, False)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
