"""Offline tests for v1.4.23 problem reports and diagnostics.

- Redaction: credentials, IPs, the household unit and session values never
  reach the summary, the diagnostics data or the GitHub link.
- The link stays under GitHub's URL budget, trimming the summary before the
  user's own text.
- The iPark snapshot records what issue #3 needed: the last result per device
  class and room, without debug logging.

Loads the real iparkapp.py with stubbed Home Assistant / aiohttp modules, like
test_poll_backoff.py, and report.py as is (it has no HA imports).
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

# iparkapp_const is pure stdlib: load the real thing so RESULT_OK /
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


_rspec = importlib.util.spec_from_file_location("bst.report", f"{REPO}/report.py")
report = importlib.util.module_from_spec(_rspec)
sys.modules["bst.report"] = report
_rspec.loader.exec_module(report)

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


USER = "kimtester"
PASSWORD = "S3cret#pw!"
SERVER_IP = "220.79.141.134"
ENTRY_DATA = {
    "iparkapp_site": {
        "sitecode": "0051",
        "sitename": "위례2차아이파크",
        "ip": SERVER_IP,
        "lat": "127.1",
        "lng": "37.4",
    },
    "iparkapp_username": USER,
    "iparkapp_password": PASSWORD,
}
SECRETS = report.collect_secrets(
    ENTRY_DATA,
    {"unique_id": f"iparkapp:{SERVER_IP}:{USER}", "title": f"위례2차아이파크 — {USER}"},
)

DENY = (
    '<imap ver="1.0" address="10.13.10.4" sender="1613동 1004호">'
    '<service type="reply" name="remote_access_light" result="deny"/></imap>'
)
OK_LIGHTS = (
    '<imap ver="1.0" address="10.13.10.4" sender="1613동 1004호">'
    '<service type="reply" name="remote_access_livinglight" result="ok">'
    '<status_map dev_num="1" unit_cnt="2"/>'
    '<status_info unit_num="switch1" unit_status="off"/>'
    '<status_info unit_num="switch2" unit_status="on"/>'
    "</service></imap>"
)


def make_api(bodies):
    api = ip.BestinIparkAppAPI.__new__(ip.BestinIparkAppAPI)
    api._poll_cycle = 0
    api._class_fatal_streak = {}
    api._class_ever_ok = set()
    api._class_next_probe = {}
    api._class_backed_off = set()
    api._room_exists = {}
    api._temper_room_next = {}
    api._unit_cnt = {}
    api.site = ENTRY_DATA["iparkapp_site"]
    api.room_sensors = {}
    api._refresh_failures = 0
    api.last_update_time = ip.datetime.now()
    api.last_sess_refresh = ip.datetime.now()
    api.dispatched = []
    api._dispatch_status = lambda *a: api.dispatched.append(a[2:4])

    async def _request(path, params, *, referer_path="/", quiet=False):
        return bodies.pop(0) if bodies else None

    api._request = _request
    return api


# --- iPark snapshot: what issue #3 needed ------------------------------------
LIGHT = ipc.DEVICE_CLASSES["light"]
LIVING = ipc.DEVICE_CLASSES["livinglight"]
api = make_api([DENY, OK_LIGHTS, "", None])
asyncio.run(api._fetch_class(LIGHT, 1))
asyncio.run(api._fetch_class(LIVING))
asyncio.run(api._fetch_class(LIGHT, 2))
asyncio.run(api._fetch_class(LIGHT, 3))
snap = api.diagnostics_snapshot()
status = snap["status"]
check("deny recorded per room", status["light:1"]["result"], "deny")
check("ok recorded with row count", (status["livinglight"]["result"], status["livinglight"]["rows"]), ("ok", 2))
check("empty reply named", status["light:2"]["result"], "empty")
check("no reply named", status["light:3"]["result"], "no_reply")
check("ever_ok reflects backoff state", status["livinglight"]["ever_ok"], True)
check("fail streak counted", status["light:1"]["fail_streak"], 1)
check("failed reply kept as a sample", "light:1" in snap["last_bad_reply"], True)
check("events recorded", len(snap["events"]), 4)

for _ in range(400):
    api._note("status", cls="x")
check("event log is capped", len(api.diagnostics_snapshot()["events"]), 300)

clean = report.scrub_obj({"gateway": snap, "entry": ENTRY_DATA}, SECRETS)
text = json.dumps(clean, ensure_ascii=False)
check("snapshot is JSON-safe", isinstance(text, str), True)
for secret in (USER, PASSWORD, SERVER_IP, "10.13.10.4", "1613동", "1004호", "127.1"):
    check(f"diagnostics hide {secret!r}", secret in text, False)
check("site code kept", "0051" in text, True)
check("site name kept", "위례2차아이파크" in text, True)

# --- summary and link ---------------------------------------------------------
diag = {
    "integration": {"version": "1.4.23", "ha_version": "2026.11.1", "gateway": "iparkapp", "site": "0051 위례2차아이파크"},
    "entities": {"sensor": {"total": 10, "unavailable": 0}},
    "gateway": clean["gateway"],
    "log": [{"time": "2026-11-10T10:00:00", "level": "WARNING", "message": report.scrub_text(f"Request failed http://{SERVER_IP}/x login_pwd={PASSWORD}", SECRETS)}],
}
blocks = report.build_summary_blocks(diag)
summary = "\n\n".join(blocks)
check("summary has the per-device table", "| light:1 | deny |" in summary, True)
check("summary keeps no password", PASSWORD in summary, False)
check("summary keeps no server IP", SERVER_IP in summary, False)

user_text = "조명이 안 올라와요. " * 200  # ~2,000 Korean characters
title = report.issue_title("iparkapp", "1.4.23", user_text)
url, body = report.build_issue_url(title, user_text, blocks)
check("link stays within budget", len(url) <= report.URL_BUDGET, True)
check("link points at the repo", url.startswith(report.ISSUE_NEW_URL + "?title="), True)
short_url, short_body = report.build_issue_url(title, "조명이 안 돼요", blocks)
check("short text keeps the user's words", "조명이 안 돼요" in short_body, True)
check("short text keeps the summary table", "| light:1 | deny |" in short_body, True)
check("short link within budget", len(short_url) <= report.URL_BUDGET, True)
big_blocks = blocks + ["```\n" + "x" * 20000 + "\n```"]
_, trimmed = report.build_issue_url(title, "조명이 안 돼요", big_blocks)
check("summary trimmed before the user's text", "조명이 안 돼요" in trimmed, True)
check("trimming is noted", "left out" in trimmed, True)

# --- config-flow error report (issue #4: no entry exists yet) -----------------
# A frame that looks like it came from custom_components/bestin/hub.py.
_scope = {}
exec(
    compile(
        "def broken_setup(entry):\n    return entry.data.get('gateway_mode')\n",
        "/config/custom_components/bestin/hub.py",
        "exec",
    ),
    _scope,
)
try:
    _scope["broken_setup"](None)
except AttributeError as ex:
    err = ex
flow_blocks = report.flow_error_blocks("local", err, "1.4.23", "2026.11.1", SECRETS)
flow_text = "\n".join(flow_blocks)
check("flow report names the error", "AttributeError" in flow_text, True)
check("flow report points at the BESTIN frame", "hub.py:2 broken_setup" in flow_text, True)
check("flow report leaves out other frames", "test_report.py" in flow_text, False)
check("flow report names the step", "`local`" in flow_text, True)

err_secret = ValueError(f"cannot reach {SERVER_IP} as {USER}")
leak = "\n".join(report.flow_error_blocks("iparkapp_login", err_secret, "1.4.23", "x", SECRETS))
check("flow report hides IP and user", (SERVER_IP in leak, USER in leak), (False, False))

if failures:
    print("\nFAILURES:", failures)
    sys.exit(1)
print("\nall passed")
