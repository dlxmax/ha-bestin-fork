"""iPark 웹앱 캡처에서 찾은 요청과 응답 모양 / Request and reply shapes from web app captures.

cleverk2000-code 가 #3 에서 웹앱 HAR 와 비교해 찾은 차이:
- 상태 조회는 req_unit_num 을 보내지 않아요 (난방 roomN 만 예외).
- 방 조명, 콘센트, 난방의 Referer 는 *_view 페이지예요.
- 콘센트 상태는 "unset/on" 처럼 대기전력 차단/전원 두 값일 수 있어요.
- 도어락은 "ing" 같은 값을 보낼 수 있어요.
- 서버가 명령을 거부하면 HA 에 오류를 보여 줘야 해요.

Differences cleverk2000-code found against the web app's HAR captures (#3):
status polls send no req_unit_num (except heating's roomN); room lights,
outlets and heating use the *_view pages as Referer; outlet status can be
"<standby cut>/<power>"; the doorlock can report "ing"; and a command the
server rejects must show an error in HA.

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
    "homeassistant.exceptions",
):
    _fake(_name)


class HomeAssistantError(Exception):
    pass


sys.modules["homeassistant.exceptions"].HomeAssistantError = HomeAssistantError
# @callback must pass the coroutine function through unchanged.
sys.modules["homeassistant.core"].callback = lambda func: func
sys.modules["homeassistant.core"].CoreState = types.SimpleNamespace(
    running="running", starting="starting", not_running="not_running"
)

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
for _name in ("bst.const", "bst.duty_cycle"):
    _fake(_name)
sys.modules["bst.const"].LOGGER = logging.getLogger("test")
sys.modules["bst.const"].BRAND_PREFIX = "bestin"

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


import xml.etree.ElementTree as ET

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


OK_BODY = '<imap ver="1.0"><service type="reply" result="ok"/></imap>'
FAIL_BODY = '<imap ver="1.0"><service type="reply" result="fail"/></imap>'


def make_api(bodies):
    api = ip.BestinIparkAppAPI.__new__(ip.BestinIparkAppAPI)
    api.calls = []
    api.set_calls = []
    api.devices = {}

    async def _request(path, params, *, referer_path="/", quiet=False):
        api.calls.append((dict(params), referer_path))
        return bodies.pop(0) if bodies else FAIL_BODY

    api._request = _request
    api._note = lambda *a, **k: None
    api._diag = lambda name, factory: factory()
    api._set_device = lambda *a: api.set_calls.append(a)
    return api


class Profile:
    def __init__(self, state):
        self.info = types.SimpleNamespace(state=state)
        self.updates = 0

    def update_callbacks(self):
        self.updates += 1


# --- 콘센트 상태 / outlet status ------------------------------------------
for raw, want in [
    ("on", True), ("off", False), ("unset/on", True), ("set/on", True),
    ("unset/off", False), ("set/off", False), (" SET/ON ", True),
    ("ing", None), ("", None), (None, None),
]:
    check(f"outlet_power({raw!r})", ipc.outlet_power(raw), want)

api = make_api([])
node = ET.Element("status_info")
electric = ipc.DEVICE_CLASSES["electric"]
api._dispatch_status(electric, 2, "switch1", "unset/on", node)
api._dispatch_status(electric, 2, "switch2", "set/off", node)
api._dispatch_status(electric, 2, "switch3", "ing", node)
check(
    "outlet rows dispatch power only, unknown rows skipped",
    api.set_calls,
    [("electric", 2, "1", True), ("electric", 2, "2", False)],
)

# --- 도어락 / doorlock -----------------------------------------------------
api = make_api([])
doorlock = ipc.DEVICE_CLASSES["doorlock"]
for raw in ("open", "close", "ing"):
    api._dispatch_status(doorlock, 1, "doorlock1", raw, node)
check(
    "doorlock open/close/ing -> True/False/None",
    [c[3] for c in api.set_calls],
    [True, False, None],
)

# --- 상태 조회 요청 / status request shape (web app captures) ---------------
for key, room, want_unit, want_ref in [
    ("gas", None, None, "/webapp/xml_ctrl_gas.php"),
    ("ventil", None, None, "/webapp/xml_ctrl_fan.php"),
    ("mode", None, None, "/webapp/xml_ctrl_goout.php"),
    ("temper", 3, "room3", "/webapp/xml_ctrl_heat_view.php"),
    ("light", 2, None, "/webapp/xml_ctrl_M_light_view.php"),
    ("electric", 2, None, "/webapp/xml_ctrl_electric_view_new.php"),
]:
    api = make_api([FAIL_BODY])
    api._note_status = lambda *a, **k: None
    api._poll_cycle = 0
    api._class_fatal_streak = {}
    api._class_ever_ok = set()
    api._class_next_probe = {}
    api._class_backed_off = set()
    api._room_exists = {}
    api._unit_cnt = {}
    try:
        asyncio.run(api._fetch_class(ipc.DEVICE_CLASSES[key], room))
    except Exception as err:  # noqa: BLE001
        print("  (fetch raised after the request)", type(err).__name__)
    params, referer = api.calls[0]
    check(f"{key} status req_unit_num", params.get("req_unit_num"), want_unit)
    check(f"{key} status referer", referer, want_ref)

# --- 거부된 명령 / rejected command ----------------------------------------
LIGHT = "bestin_livinglight_1_2"


def run_light(body, start):
    api = make_api([body])
    api.devices[LIGHT] = Profile(start)
    raised = None
    try:
        asyncio.run(api.enqueue_command(LIGHT, None, switch="on"))
    except HomeAssistantError as err:
        raised = err
    return api, raised


api, raised = run_light(FAIL_BODY, False)
check("rejected light raises HomeAssistantError", raised is not None, True)
check("rejected light reverts to off", api.devices[LIGHT].info.state, False)
check("revert notifies HA (flip + revert)", api.devices[LIGHT].updates, 2)

api, raised = run_light(OK_BODY, False)
check("accepted light does not raise", raised, None)
check("accepted light stays on", api.devices[LIGHT].info.state, True)

api, raised = run_light(None, False)
check("no reply (timeout) also raises", raised is not None, True)

VENT = "bestin_ventil_1"
api = make_api([FAIL_BODY])
api.devices[VENT] = Profile({"state": False, "wind_speed": "off"})
try:
    asyncio.run(api.enqueue_command(VENT, "low"))
    raised = None
except HomeAssistantError as err:
    raised = err
check("rejected ventil raises", raised is not None, True)
check(
    "rejected ventil reverts",
    api.devices[VENT].info.state,
    {"state": False, "wind_speed": "off"},
)

# --- 방 온도 센서와 HA 재시작 / room sensor across HA restarts -------------
# 다시 시작할 때 센서가 아직 없으면 월패드 값이 그래프에 튀었어요.
# On restart the sensor was not loaded yet, so the wallpad value spiked.
api = make_api([])
api.hass = types.SimpleNamespace(state="not_running")
check("setting up: sensor missing keeps previous", api._room_temperature(None, 23.0, 21.8), 21.8)
check("starting: first poll shows nothing yet", api._room_temperature(None, 23.0, None), None)
check("starting: sensor value wins", api._room_temperature(21.7, 23.0, 21.8), 21.7)
api.hass.state = "starting"
check("starting: still keeps previous", api._room_temperature(None, 23.0, 21.8), 21.8)
api.hass.state = "running"
check("running: dead sensor falls back to wallpad", api._room_temperature(None, 23.0, 21.8), 23.0)
check("running: sensor value wins", api._room_temperature(21.7, 23.0, 21.8), 21.7)

print()
print("FAILED:" if failures else "all passed", *failures)
sys.exit(1 if failures else 0)
