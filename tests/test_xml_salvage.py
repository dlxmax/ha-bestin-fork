"""Offline tests for the v1.4.12 malformed-XML salvage path.

The wallpad's ``getHomeDevice_heat.php`` **control** reply is not well-formed
XML, so a strict parse threw the whole document away — making every thermostat
command log "제어 실패 / control failed" even though the wallpad had accepted
it (observed live: 10/10 temper controls "failed", 8/8 livinglight succeeded),
and discarding the post-state the reply carried.

Loads the real iparkapp.py with stubbed Home Assistant / aiohttp modules so no
HA install is needed.
"""

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
    """Any attribute access returns another one of these, and it's hashable."""

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
for _name in ("bst.const", "bst.duty_cycle", "bst.iparkapp_const"):
    _fake(_name)
sys.modules["bst.const"].LOGGER = logging.getLogger("test")

spec = importlib.util.spec_from_file_location("bst.iparkapp", f"{REPO}/iparkapp.py")
ip = importlib.util.module_from_spec(spec)
sys.modules["bst.iparkapp"] = ip
spec.loader.exec_module(ip)

parse = ip.BestinIparkAppAPI._parse_xml_result

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


# The real shape, reconstructed from the live log: header + result are intact,
# the document as a whole doesn't close properly.
MALFORMED = (
    '<?xml version="1.0" encoding="utf-8"?>\r\n'
    '<imap ver = "1.0" address="10.13.10.4" sender ="1613동 1004호">\r\n'
    '<service type = "reply" name="remote_access_temper" result="ok"/>\r\n'
    '<target name="internet" id="1">\r\n'
    '<status_map unit_cnt="5"/>\r\n'
    '<status_info unit_num="room5" unit_status="off/22/29"/>\r\n'
    "</imap>\r\n"
)

WELL_FORMED = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<imap ver="1.0">\n'
    '<service type="reply" name="remote_access_livinglight" result="ok"/>\n'
    '<status_info unit_num="switch1" unit_status="on"/>\n'
    "</imap>\n"
)

# --- the bug: a malformed reply that actually said result="ok" --------------
result, root = parse(MALFORMED)
check("malformed reply reports its real result", result, "ok")
check("  ...status_info recovered", root is not None and len(root.findall(".//status_info")), 1)
check(
    "  ...attributes intact",
    root.find(".//status_info").get("unit_status"),
    "off/22/29",
)
check("  ...unit_num intact", root.find(".//status_info").get("unit_num"), "room5")
check("  ...status_map recovered too", root.find(".//status_map").get("unit_cnt"), "5")

# --- well-formed replies must still take the strict path unchanged ----------
result, root = parse(WELL_FORMED)
check("well-formed still parses", result, "ok")
check("  ...row preserved", root.find(".//status_info").get("unit_num"), "switch1")

# --- genuine failures must stay failures ------------------------------------
check("empty body -> None", parse("")[0], None)
check("None body -> None", parse(None)[0], None)
check("whitespace body -> None", parse("   \r\n ")[0], None)
check("non-xml garbage -> None", parse("<<<not xml at all")[0], None)

# A malformed reply carrying a real error must report that error, not "ok".
FAILED = MALFORMED.replace('result="ok"', 'result="fail"')
check("malformed + fail reports fail", parse(FAILED)[0], "fail")

# Malformed with no <service> at all is unusable -> genuine failure.
NO_SERVICE = '<imap ver="1.0">\n<status_info unit_num="room1"/>\n</imap_broken>'
check("malformed, no <service> -> None", parse(NO_SERVICE)[0], None)

# --- multi-row salvage -------------------------------------------------------
MULTI = (
    '<imap ver="1.0">\n'
    '<service type="reply" result="ok"/>\n'
    '<status_info unit_num="room1" unit_status="on/24/23"/>\n'
    '<status_info unit_num="room2" unit_status="off/20/22"/>\n'
    "</imap_unclosed>"
)
result, root = parse(MULTI)
check("multi-row malformed: result", result, "ok")
check(
    "  ...all rows recovered",
    [e.get("unit_num") for e in root.findall(".//status_info")],
    ["room1", "room2"],
)

# Self-closing vs. open tag spelling shouldn't matter.
OPEN_TAG = MULTI.replace('unit_status="on/24/23"/>', 'unit_status="on/24/23">')
result, root = parse(OPEN_TAG)
check("open-tag spelling still recovered", result, "ok")
check(
    "  ...rows still found",
    [e.get("unit_num") for e in root.findall(".//status_info")],
    ["room1", "room2"],
)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
