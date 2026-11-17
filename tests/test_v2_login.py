"""Offline test for issues #11 and #12: Smart Home 2.0 login.

Since 2026-11-17 the complex servers refuse every /v2/api request with nginx
"401 Authorization Required", while /v3/auth/login still returns 200. The
official app (com.mobiletalk.valley 1.5.4) logs in with an X-API-KEY header
and the body "V2"; ours sent neither.

  1. The session refresh (center.py) and the setup login (config_flow.py)
     both send X-API-KEY, the UUID as Authorization, and the body "V2".
  2. Content-Type stays application/json, as in the app.
  3. const.py carries the app's key and body unchanged.
  4. The refreshed session is stored in the config entry.

Uses the real aiohttp against a local server standing in for
center.hdc-smart.com. Run with: uv run --with aiohttp python tests/test_v2_login.py
"""

import asyncio
import importlib.util
import logging
import os
import re
import sys
import types

from aiohttp import ClientSession, web

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.join(ROOT, "custom_components", "bestin")

# The key in the app bundle (main.59b46280de06d4c9.js, xApiKey()).
APP_KEY = (
    "ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5LmV5SnpaV055WlhRaU9pSXhNak0w"
    "TlRZM09Ea3dJaXdpYm1GdFpTSTZJbk50WVhKMGFHOXRaU0o5Ljk5YjBNYWtXUkNaSzhhVExkOW1X"
    "OFlXanR5VnNpd2k5NmNlWjNkYzZzWFk"
)


class _Permissive:
    def __getattr__(self, name):
        return _Permissive()

    def __call__(self, *a, **kw):
        return _Permissive()

    def __iter__(self):
        return iter(())


class _Base:
    """Stands in for Home Assistant base classes (ConfigFlow, OptionsFlow)."""

    def __init_subclass__(cls, **kwargs):
        pass


def _fake(name, **attrs):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda attr: _Permissive()
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


for _name in (
    "xmltodict",
    "voluptuous",
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.climate",
    "homeassistant.components.climate.const",
    "homeassistant.components.light",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.event",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.selector",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.loader",
):
    _fake(_name)
_fake("homeassistant.config_entries", ConfigFlow=_Base, OptionsFlow=_Base)
_fake("homeassistant.const", Platform=_Permissive())
ha_const = sys.modules["homeassistant.const"]
for _key in ("CONF_IP_ADDRESS", "CONF_USERNAME", "CONF_PASSWORD", "CONF_UUID",
             "CONF_SCAN_INTERVAL", "CONF_URL", "CONF_PORT", "CONF_TYPE"):
    setattr(ha_const, _key, _key.lower().removeprefix("conf_"))
sys.modules["homeassistant.core"].callback = lambda func: func

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
for _name in ("bst.controller", "bst.until", "bst.hub", "bst.iparkapp",
              "bst.report", "bst.iparkapp_const", "bst.diagnostics"):
    _fake(_name)


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, f"{REPO}/{filename}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("bst.const", "const.py")
center = _load("bst.center", "center.py")
config_flow = _load("bst.config_flow", "config_flow.py")

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got {got!r}, want {want!r}")
    if not ok:
        failures.append(name)


logins: list[dict] = []


async def login_handler(request):
    body = await request.text()
    logins.append({"headers": dict(request.headers), "body": body})
    # Like the server since 11-17: a token only works when the login came in
    # the app's way. Without it, 200 with a token the API refuses.
    good = request.headers.get("X-API-KEY") == APP_KEY and body == "V2"
    token = "GOOD" if good else "REFUSED"
    return web.json_response({"access-token": token, "url": "https://x.example"})


async def main():
    app = web.Application()
    app.router.add_post("/v3/auth/login", login_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    login_url = f"http://127.0.0.1:{port}/v3/auth/login"

    # --- const.py --------------------------------------------------------
    check("real login URL", const.V2_LOGIN_URL, "https://center.hdc-smart.com/v3/auth/login")
    check("app key unchanged", const.V2_API_KEY, APP_KEY)
    check("app body", const.V2_LOGIN_BODY, "V2")

    center.V2_LOGIN_URL = login_url
    config_flow.V2_LOGIN_URL = login_url

    # --- session refresh (center.py) --------------------------------------
    stored = {}

    class Entries:
        def async_update_entry(self, entry, data):
            stored.update(data)
            entry.data = data

    class Hass:
        config_entries = Entries()

        def create_task(self, coro):
            return asyncio.ensure_future(coro)

    class Entry:
        data = {"uuid": "UUID", "session": {"access-token": "OLD", "url": "u"}}
        options = {}

    api = center.BestinCenterAPI(
        Hass(), Entry(), {}, "hub", "Smart Home 2.0", lambda *a: None
    )
    await api._v2_refresh_session()
    sent = logins[-1]
    check("refresh sends X-API-KEY", sent["headers"].get("X-API-KEY"), APP_KEY)
    check("refresh sends the UUID", sent["headers"].get("Authorization"), "UUID")
    check("refresh body", sent["body"], "V2")
    check("refresh Content-Type", sent["headers"].get("Content-Type"), "application/json")
    check("refreshed token stored", stored.get("session", {}).get("access-token"), "GOOD")
    await api.session.close()

    # --- setup login (config_flow.py) -------------------------------------
    flow_cls = next(
        v for v in vars(config_flow).values()
        if isinstance(v, type) and hasattr(v, "_v2_server_login")
    )
    flow = object.__new__(flow_cls)
    async with ClientSession() as session:
        resp, err = await flow._v2_server_login({"uuid": "NEWUUID"}, session)
    sent = logins[-1]
    check("setup sends X-API-KEY", sent["headers"].get("X-API-KEY"), APP_KEY)
    check("setup sends the UUID", sent["headers"].get("Authorization"), "NEWUUID")
    check("setup body", sent["body"], "V2")
    check("setup Content-Type", sent["headers"].get("Content-Type"), "application/json")
    check("setup gets a usable token", (resp or {}).get("access-token"), "GOOD")
    check("setup no error", err, None)

    await runner.cleanup()


asyncio.run(main())
print("\nall passed" if not failures else f"\nFAILURES: {failures}")
sys.exit(1 if failures else 0)
