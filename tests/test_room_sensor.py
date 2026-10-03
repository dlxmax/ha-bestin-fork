"""Offline tests for the v1.4.16 per-room temperature sensor option.

Through the iPark web app the wallpad's temperature arrives as whole degrees,
rounded down (the wall unit itself shows halves), and the wall unit reads high. A mapped HA
sensor drives the duty cycle instead, but ON pulses must still be computed
from the wallpad's own reading because the wallpad compares the setpoint to
its own sensor.
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

pkg = types.ModuleType("bst")
pkg.__path__ = [REPO]
sys.modules["bst"] = pkg
const = types.ModuleType("bst.const")
const.LOGGER = logging.getLogger("test")
sys.modules["bst.const"] = const

spec = importlib.util.spec_from_file_location("bst.duty_cycle", f"{REPO}/duty_cycle.py")
dc = importlib.util.module_from_spec(spec)
sys.modules["bst.duty_cycle"] = dc
spec.loader.exec_module(dc)

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def make():
    sent = []

    async def _send(room, ctrl):
        sent.append((room, ctrl))

    return dc.DutyCycleController(send_command=_send), sent


# --- control temperature ----------------------------------------------------
st = dc.RoomDutyCycleState(room=1)
check("no readings -> no control temp", st.control_temp, None)
st.current_temp = 27.0
check("wallpad only -> wallpad", st.control_temp, 27.0)
st.sensor_temp = 24.9
check("sensor wins over wallpad", st.control_temp, 24.9)
st.sensor_temp = None
check("sensor gone -> back to wallpad", st.control_temp, 27.0)

# --- no "on/5" before the first poll ----------------------------------------
c, sent = make()
c.set_preset(1, "comfort")               # 22 °C
c.set_sensor_temp(1, 19.0)               # cold room, but no wallpad reading yet
asyncio.run(c._tick())
check("no pulse before the wallpad has reported", sent, [])

# --- sensor decides, wallpad sets the forced setpoint -----------------------
c.upsert_current_temp(1, 25.0)           # wallpad reads high
asyncio.run(c._tick())
check("cold sensor turns the room on, forced above the wallpad",
      sent, [(1, "on/30")])
check("  ...full duty from the sensor error", c.rooms[1].target_duty_pct, 100.0)

# Wallpad alone (25) would be above the 22 setpoint and never heat.
c2, sent2 = make()
c2.set_preset(1, "comfort")
c2.upsert_current_temp(1, 25.0)
asyncio.run(c2._tick())
check("same room without a sensor stays off", sent2, [(1, "off/22")])

# Decimal sensor gives a proportional duty the whole-degree wallpad can't.
c3, _ = make()
c3.set_preset(1, "comfort")              # band 2.0
c3.upsert_current_temp(1, 25.0)
c3.set_sensor_temp(1, 21.3)
duty = c3._compute_duty(c3.rooms[1], dc.PRESET_PROFILES["comfort"])
check("decimal sensor -> fine-grained duty", round(duty, 1), 35.0)


# --- iparkapp: sensor state parsing -----------------------------------------
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
sys.modules["homeassistant.const"].ATTR_UNIT_OF_MEASUREMENT = "unit_of_measurement"
sys.modules["homeassistant.const"].UnitOfTemperature = types.SimpleNamespace(
    FAHRENHEIT="°F", CELSIUS="°C"
)
for _name in ("bst.notify", "bst.errors"):
    _fake(_name)
const.__getattr__ = lambda attr: _Permissive()   # rest of bst.const

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


def S(state, unit="°C"):
    return types.SimpleNamespace(state=state, attributes={"unit_of_measurement": unit})


check("option key", ipc.room_temp_sensor_key(3), "room_temp_sensor_3")
check("celsius passes through", ip.room_sensor_celsius(S("24.9")), 24.9)
check("fahrenheit converted", ip.room_sensor_celsius(S("77", "°F")), 25.0)
check("unavailable -> None", ip.room_sensor_celsius(S("unavailable")), None)
check("unknown -> None", ip.room_sensor_celsius(S("unknown")), None)
check("missing entity -> None", ip.room_sensor_celsius(None), None)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
