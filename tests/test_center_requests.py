"""Offline tests for issue #8: elevator 401 and server request records.

  1. The elevator call and the SSE status request send access-token (the
     SSE request used to send no headers at all).
  2. Every request to the server is recorded for diagnostics: method, host
     and path (never the query string, which carries the v1 login), status,
     and the start of the reply when the server refuses.
  3. Reading an error reply for the record still lets the caller read it.

Uses the real aiohttp against a local test server, with Home Assistant
stubbed. Run with: uv run --with aiohttp python tests/test_center_requests.py
"""

import asyncio
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


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, f"{REPO}/{filename}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


center = _load("bst.center", "center.py")

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got {got!r}, want {want!r}")
    if not ok:
        failures.append(name)


seen: dict[str, dict] = {}


async def apply_handler(request):
    seen["apply"] = dict(request.headers)
    if request.headers.get("access-token") != "TOKEN":
        return web.Response(status=401, text='{"err":"invalid token"}')
    return web.Response(text='{"result":"ok"}', content_type="text/plain")


async def sse_handler(request):
    seen["sse"] = dict(request.headers)
    resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
    await resp.prepare(request)
    await resp.write(b'data: {"address": "other"}\n\n')
    return resp


async def refused_handler(request):
    return web.Response(status=401, text="denied: " + "x" * 400)


async def main():
    app = web.Application()
    app.router.add_post("/v2/admin/elevators/home/apply", apply_handler)
    app.router.add_get("/v2/admin/elevators/sse", sse_handler)
    app.router.add_get("/refused", refused_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    class Entry:
        data = {
            "uuid": "UUID",
            "ip_address": "addr",
            "session": {"url": base, "access-token": "TOKEN"},
        }
        options = {}

    class Hass:
        def create_task(self, coro):
            return asyncio.ensure_future(coro)

    api = center.BestinCenterAPI(
        Hass(), Entry(), {}, "hub", "Smart Home 2.0", lambda *a: None
    )
    api.result_after_request = lambda resp: resp.get("result")

    await api.elevator_call_request()
    await asyncio.sleep(0.3)
    check("call sends access-token", seen.get("apply", {}).get("access-token"), "TOKEN")
    check("call keeps the UUID", seen.get("apply", {}).get("Authorization"), "UUID")
    check("SSE sends access-token", seen.get("sse", {}).get("access-token"), "TOKEN")
    check("SSE sends the UUID", seen.get("sse", {}).get("Authorization"), "UUID")

    events = list(api.request_events)
    check("both requests recorded",
          [(e["method"], e["path"], e["status"]) for e in events],
          [("POST", "/v2/admin/elevators/home/apply", 200),
           ("GET", "/v2/admin/elevators/sse", 200)])
    check("no body kept for a 200", events[0]["body"], None)

    async with api.session.get(f"{base}/refused?login_pwd=secret") as resp:
        caller_text = await resp.text()
    last = api.request_events[-1]
    check("refusal recorded", (last["status"], last["path"]), (401, "/refused"))
    check("refusal body kept, cut to 200", last["body"], ("denied: " + "x" * 400)[:200])
    check("query string never kept", "secret" in str(last), False)
    check("caller still reads the body", caller_text.startswith("denied:"), True)

    try:
        async with api.session.get("http://127.0.0.1:1/") as _:
            pass
    except Exception:  # noqa: BLE001 - refused on purpose
        pass
    snap = api.diagnostics_snapshot()
    check("connection errors recorded", "error" in snap["events"][-1], True)
    check("snapshot carries the records", len(snap["events"]), 4)

    await api.session.close()
    await runner.cleanup()


asyncio.run(main())
print("\nall passed" if not failures else f"\nFAILURES: {failures}")
sys.exit(1 if failures else 0)
