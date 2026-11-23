"""연결 안정화 시험 / ConnectionManager: connect timeout, TCP keepalive, bounded close.

Loads only ConnectionManager (and CLOSE_TIMEOUT) out of hub.py, so Home Assistant is not needed.
Run: python3 -I tests/test_connection_hardening.py [path/to/hub.py]
"""
import ast
import asyncio
import logging
import re
import socket
import sys
import time
import types
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "custom_components/bestin/hub.py")
tree = ast.parse(SRC.read_text(encoding="utf-8"))
keep = [n for n in tree.body if (isinstance(n, ast.ClassDef) and n.name == "ConnectionManager")
        or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "CLOSE_TIMEOUT" for t in n.targets))]
fake_asyncio = types.SimpleNamespace(**{k: getattr(asyncio, k) for k in dir(asyncio) if not k.startswith("__")})
ns: dict = {"asyncio": fake_asyncio, "re": re, "socket": socket, "time": time, "LOGGER": logging.getLogger("t"),
            "serial_asyncio": None}
exec(compile(ast.Module(keep, []), str(SRC), "exec"), ns)
ConnectionManager = ns["ConnectionManager"]
failures: list[str] = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


async def bounded(name, coro):
    """Run a scenario; a hang is reported as a failure instead of blocking the test."""
    try:
        return await asyncio.wait_for(coro, timeout=5)
    except asyncio.TimeoutError:
        print(f"FAIL {name}: hung for more than 5 s", flush=True)
        failures.append(name)
        return None


async def main() -> None:
    srv = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]

    # 1. Keepalive is on for a socket connection.
    cm = ConnectionManager(f"127.0.0.1:{port}")
    check("connect to a live adapter", await cm.connect(), True)
    sock = cm.writer.get_extra_info("socket")
    check("SO_KEEPALIVE enabled", sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0, True)
    if hasattr(socket, "TCP_KEEPIDLE"):
        check("keepalive idle 20 s", sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE), 20)
    if hasattr(socket, "TCP_USER_TIMEOUT"):
        check("TCP user timeout 45 s", sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_USER_TIMEOUT), 45000)
    await cm.close()

    # 2. An address that never answers must not hang connect(): it honours `timeout`.
    async def never(*a, **k):
        await asyncio.sleep(3600)
    fake_asyncio.open_connection = never
    cm2 = ConnectionManager("10.255.255.1:8899")
    t0 = time.monotonic()
    name = "connect to a silent address fails fast"
    ok = await bounded(name, cm2.connect(timeout=0.3))
    if name not in failures:
        check(name, (ok, time.monotonic() - t0 < 2, cm2.is_connected()), (False, True, False))
    fake_asyncio.open_connection = asyncio.open_connection

    # 3. Closing a dead peer's socket is bounded and falls back to abort().
    ns["CLOSE_TIMEOUT"] = 0.2
    aborted: list[bool] = []

    class DeadWriter:
        transport = types.SimpleNamespace(abort=lambda: aborted.append(True))

        def close(self):
            pass

        async def wait_closed(self):
            await asyncio.sleep(3600)

    cm3 = ConnectionManager(f"127.0.0.1:{port}")
    cm3.writer = DeadWriter()
    t0 = time.monotonic()
    name = "close of a dead peer returns quickly, aborts, forgets the writer"
    await bounded(name, cm3._close_writer())
    if name not in failures:
        check(name, (time.monotonic() - t0 < 2, aborted, cm3.writer), (True, [True], None))
    # 4. The serial open is bounded the same way.
    async def never_serial(**k):
        await asyncio.sleep(3600)
    ns["serial_asyncio"] = types.SimpleNamespace(open_serial_connection=never_serial)
    cm4 = ConnectionManager("/dev/ttyUSB0")
    name = "open of a stuck serial port fails fast"
    t0 = time.monotonic()
    ok = await bounded(name, cm4.connect(timeout=0.3))
    if name not in failures:
        check(name, (ok, time.monotonic() - t0 < 2), (False, True))
    srv.close()


asyncio.run(main())
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
