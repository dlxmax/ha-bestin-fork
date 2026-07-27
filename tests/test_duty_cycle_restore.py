"""Offline tests for the v1.4.11 duty-cycle restore / release logic.

Loads the real duty_cycle.py with a stubbed `.const` so no Home Assistant
install is needed.
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


def make(send=None):
    sent = []

    async def _send(room, ctrl):
        sent.append((room, ctrl))
        if send is not None:
            await send(room, ctrl)

    return dc.DutyCycleController(send_command=_send), sent


# --- restore_room -----------------------------------------------------------
c, _ = make()
check("unknown preset rejected", c.restore_room(3, "banana"), False)
check("  ...creates no room", 3 in c.rooms, False)

c, _ = make()
check("'none' preset not restored", c.restore_room(3, "none"), False)
check("  ...creates no room", 3 in c.rooms, False)

c, _ = make()
check("eco restored", c.restore_room(3, "eco"), True)
check("  ...preset set", c.rooms[3].preset, "eco")
check("  ...canonical setpoint", c.rooms[3].user_setpoint, 20.0)
check("  ...phase unknown (re-asserts)", c.rooms[3].last_sent_phase, None)

# Custom setpoint must survive set_preset's canonical-value reset.
c, _ = make()
c.restore_room(3, "eco", 18.5)
check("custom setpoint wins over canonical", c.rooms[3].user_setpoint, 18.5)

# String room keys (device_info.room is a display string) share one keyspace.
c, _ = make()
c.restore_room("4", "comfort", 21.0)
check("string room key normalised", list(c.rooms.keys()), [4])
check("  ...reachable as int", c.get_room(4).preset, "comfort")

# --- release ----------------------------------------------------------------
c, sent = make()
c.restore_room(3, "eco", 18.0)
c.rooms[3].last_sent_phase = True          # mid ON pulse: setpoint is inflated
asyncio.run(c.release())
check("ON-phase room handed back", sent, [(3, "on/18")])
check("  ...phase cleared", c.rooms[3].last_sent_phase, None)

c, sent = make()
c.restore_room(3, "eco", 18.0)
c.rooms[3].last_sent_phase = False         # already OFF: wallpad has true setpoint
asyncio.run(c.release())
check("OFF-phase room left alone", sent, [])

c, sent = make()
c.set_preset(3, "none")
c.rooms[3].last_sent_phase = True
asyncio.run(c.release())
check("'none' preset room left alone", sent, [])

c, sent = make()
asyncio.run(c.release())
check("no rooms -> no traffic", sent, [])

# Multiple rooms released together.
c, sent = make()
for r in (1, 2, 5):
    c.restore_room(r, "comfort", 22.0)
    c.rooms[r].last_sent_phase = True
asyncio.run(c.release())
check("all ON rooms handed back", sorted(sent), [(1, "on/22"), (2, "on/22"), (5, "on/22")])


# A failing send must not raise, must not block the other rooms, and must
# leave the phase alone so the failure is visible rather than assumed fixed.
async def boom(room, ctrl):
    if room == 2:
        raise RuntimeError("server down")


c, sent = make(send=boom)
for r in (1, 2):
    c.restore_room(r, "comfort", 22.0)
    c.rooms[r].last_sent_phase = True
asyncio.run(c.release())
check("failure does not raise / others proceed", sorted(sent), [(1, "on/22"), (2, "on/22")])
check("  ...failed room keeps ON phase", c.rooms[2].last_sent_phase, True)
check("  ...ok room cleared", c.rooms[1].last_sent_phase, None)


# A hung send must not block shutdown past the timeout budget.
async def hang(room, ctrl):
    await asyncio.sleep(60)


async def timed_release():
    c, sent = make(send=hang)
    c.restore_room(1, "comfort", 22.0)
    c.rooms[1].last_sent_phase = True
    dc.RELEASE_TIMEOUT_S = 1
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    await c.release()
    return loop.time() - t0


elapsed = asyncio.run(timed_release())
check("hung send times out (<3s)", elapsed < 3, True)


# --- stop() drives release --------------------------------------------------
async def stop_releases():
    c, sent = make()
    c.restore_room(3, "eco", 19.0)
    c.rooms[3].last_sent_phase = True
    await c.stop()          # never started; must still release
    return sent


check("stop() hands rooms back", asyncio.run(stop_releases()), [(3, "on/19")])

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
