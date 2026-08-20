"""Offline tests for v1.4.13 central-server outage handling.

The complex server goes down as a whole from time to time (the phone app
shows "알림 호출에 실패했습니다" when it does). Setup used to fail with a bare
"Error setting up entry" and no retry cadence of its own. These tests cover
the three things that changed:

  1. login failures are classified (unreachable server vs rejected password),
  2. setup retries on a five-minute cadence instead of HA's ~80 s hammering,
  3. the user is told through a persistent notification, and the notification
     clears itself on recovery.

Loads the real modules with stubbed Home Assistant / aiohttp packages, the
same way test_poll_backoff.py does.
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
    "homeassistant.exceptions",
    "homeassistant.helpers",
    "homeassistant.helpers.event",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_registry",
):
    _fake(_name)


class ClientError(Exception):
    """Stand-in for aiohttp.ClientError."""


sys.modules["aiohttp"].ClientError = ClientError


class ConfigEntryNotReady(Exception):
    """Stand-in for the real HA exception (must be a real class to raise)."""


sys.modules["homeassistant.exceptions"].ConfigEntryNotReady = ConfigEntryNotReady
# @callback must stay identity, otherwise the decorated coroutines vanish.
sys.modules["homeassistant.core"].callback = lambda func: func

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
for _name in ("bst.const", "bst.duty_cycle", "bst.hub"):
    _fake(_name)
sys.modules["bst.const"].LOGGER = logging.getLogger("test")
sys.modules["bst.const"].DOMAIN = "bestin"
sys.modules["bst.const"].PLATFORMS = []


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, f"{REPO}/{filename}")
    # __init__.py would otherwise be treated as a package of its own, making
    # its ``from .hub import ...`` bypass the stubs and load the real hub.
    spec.submodule_search_locations = None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


ipc = _load("bst.iparkapp_const", "iparkapp_const.py")
errors = _load("bst.errors", "errors.py")

# notify.py imports homeassistant.components.persistent_notification; record
# calls instead of stubbing it away so the retry path's messaging is asserted.
notifications = []


class _FakeNotify(types.ModuleType):
    def async_create(self, hass, message, title=None, notification_id=None):
        notifications.append(("create", notification_id, title, message))

    def async_dismiss(self, hass, notification_id):
        notifications.append(("dismiss", notification_id, None, None))


notify_stub = _FakeNotify("bst.notify")
notify_stub.async_notify_unavailable = lambda hass, entry, detail, retry_minutes=None: (
    notifications.append(("unavailable", entry.entry_id, retry_minutes, detail))
)
notify_stub.async_notify_auth_failed = lambda hass, entry, detail: (
    notifications.append(("auth_failed", entry.entry_id, None, detail))
)
notify_stub.async_clear_unavailable = lambda hass, entry: (
    notifications.append(("clear", entry.entry_id, None, None))
)
sys.modules["bst.notify"] = notify_stub

ip = _load("bst.iparkapp", "iparkapp.py")
entry_mod = _load("bst.entry", "__init__.py")

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


# ---------------------------------------------------------------------------
# 1. Login failure classification
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, payload=None, raise_exc=None):
        self._payload = payload
        self._raise = raise_exc

    async def __aenter__(self):
        if self._raise is not None:
            raise self._raise
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    async def json(self, content_type=None):
        return self._payload


class _Session:
    """Scripted aiohttp session: GET always fine, POST returns a payload."""

    def __init__(self, post_payload=None, get_exc=None, post_exc=None):
        self._post_payload = post_payload
        self._get_exc = get_exc
        self._post_exc = post_exc

    def get(self, *a, **kw):
        return _Resp(raise_exc=self._get_exc)

    def post(self, *a, **kw):
        return _Resp(payload=self._post_payload, raise_exc=self._post_exc)


def make_api(session):
    api = ip.BestinIparkAppAPI.__new__(ip.BestinIparkAppAPI)
    api.host = "10.0.0.1"
    api.site = {}
    api.username = "u"
    api.password = "p"
    api.session = session
    api._refresh_failures = 0
    api.hass = _Permissive()
    api.entry = types.SimpleNamespace(entry_id="e1")
    return api


def login_error(session):
    try:
        asyncio.run(make_api(session)._login())
    except Exception as ex:  # noqa: BLE001 — the type is what's under test
        return type(ex).__name__
    return None


check("server down (connection error) -> connection error",
      login_error(_Session(get_exc=ClientError("connection refused"))),
      "IparkAppConnectionError")
check("timeout -> connection error",
      login_error(_Session(get_exc=asyncio.TimeoutError())),
      "IparkAppConnectionError")
check("non-JSON reply -> connection error",
      login_error(_Session(post_exc=ClientError("not json"))),
      "IparkAppConnectionError")
check("server-side failure payload -> connection error (not a password prompt)",
      login_error(_Session(post_payload={"ret": "error", "msg": "server busy"})),
      "IparkAppConnectionError")
check("credential rejection ('_fair') -> auth error",
      login_error(_Session(post_payload={"ret": "login_fair", "msg": "bad pw"})),
      "IparkAppAuthError")
check("success -> no error",
      login_error(_Session(post_payload={"ret": "success"})),
      None)


# ---------------------------------------------------------------------------
# 2. Session refresh: notify only after a run of failures, clear on recovery
# ---------------------------------------------------------------------------

notifications.clear()
api = make_api(_Session())
calls = {"n": 0}


async def _failing_login():
    calls["n"] += 1
    raise errors.IparkAppConnectionError("server down")


api._login = _failing_login
asyncio.run(api._scheduled_refresh(None))
check("one refresh failure stays silent",
      [n for n in notifications if n[0] == "unavailable"], [])
asyncio.run(api._scheduled_refresh(None))
check("second consecutive failure notifies",
      len([n for n in notifications if n[0] == "unavailable"]), 1)


async def _ok_login():
    return None


api._login = _ok_login
notifications.clear()
asyncio.run(api._scheduled_refresh(None))
check("recovery clears the notification",
      [n[0] for n in notifications], ["clear"])
check("  ...and resets the streak", api._refresh_failures, 0)


# ---------------------------------------------------------------------------
# 3. Setup retry cadence
# ---------------------------------------------------------------------------


class _Hass:
    def __init__(self):
        self.data = {"bestin": {}}
        self.loop = self
        self._t = 0.0

    def time(self):
        return self._t

    def advance(self, seconds):
        self._t += seconds


class _Hub:
    def __init__(self, exc=None):
        self.exc = exc
        self.attempts = 0
        self.closed = 0

    async def async_initialize_iparkapp(self):
        self.attempts += 1
        if self.exc is not None:
            raise self.exc

    async def async_close(self):
        self.closed += 1


entry = types.SimpleNamespace(entry_id="e1", data={})


def setup(hass, hub):
    hass.data["bestin"][entry.entry_id] = hub
    try:
        asyncio.run(entry_mod._async_setup_iparkapp(hass, entry, hub))
    except ConfigEntryNotReady as ex:
        return str(ex)
    return None


entry_mod._LAST_IPARKAPP_ATTEMPT.clear()
notifications.clear()
hass = _Hass()
down = _Hub(errors.IparkAppConnectionError("server down"))

check("outage raises ConfigEntryNotReady (HA retries) not a hard error",
      setup(hass, down) is not None, True)
check("  ...user is notified", [n[0] for n in notifications], ["unavailable"])
check("  ...with the retry interval in minutes",
      notifications[0][2], entry_mod.IPARKAPP_RETRY_SECONDS // 60)
check("  ...and the half-built hub is closed", down.closed, 1)
check("  ...entry data is not left behind",
      entry.entry_id in hass.data["bestin"], False)

# HA's own backoff fires several times inside the five-minute window; none of
# those may touch the network again.
for _ in range(3):  # 3 x 80 s = 240 s, still inside the 300 s window
    hass.advance(80)
    setup(hass, down)
check("HA backoff retries inside the window do not re-hit the server",
      down.attempts, 1)

hass.advance(entry_mod.IPARKAPP_RETRY_SECONDS)
setup(hass, down)
check("a real attempt happens once the 5 minutes elapse", down.attempts, 2)

# Recovery.
notifications.clear()
up = _Hub()
hass.advance(entry_mod.IPARKAPP_RETRY_SECONDS)
check("recovery sets up cleanly", setup(hass, up), None)
check("  ...notification cleared", [n[0] for n in notifications], ["clear"])
check("  ...cooldown state released",
      entry.entry_id in entry_mod._LAST_IPARKAPP_ATTEMPT, False)

# Credential rejection: notified differently, still retried (never a dead entry).
entry_mod._LAST_IPARKAPP_ATTEMPT.clear()
notifications.clear()
bad_pw = _Hub(errors.IparkAppAuthError("bad password"))
check("auth failure also yields ConfigEntryNotReady",
      setup(_Hass(), bad_pw) is not None, True)
check("  ...with the auth-specific notification",
      [n[0] for n in notifications], ["auth_failed"])

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
