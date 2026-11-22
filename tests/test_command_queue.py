"""명령 대기열 시험 / AsyncQueue must be a FIFO whose peek does not rotate the queue (#14).

Run: python3 -I tests/test_command_queue.py [path/to/controller.py]

Loads only the AsyncQueue class out of controller.py (Home Assistant is not needed).
"""
import ast
import asyncio
import sys
from collections import deque
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "custom_components/bestin/controller.py")
tree = ast.parse(SRC.read_text())
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AsyncQueue")
ns: dict = {"asyncio": asyncio, "deque": deque}
exec(compile(ast.Module([cls], []), str(SRC), "exec"), ns)
AsyncQueue = ns["AsyncQueue"]


async def main() -> None:
    q = AsyncQueue()
    a, b, c = {"n": "A"}, {"n": "B"}, {"n": "C"}
    for item in (a, b, c):
        await q.put(item)

    # One peek per received frame while the bus is busy: the head must not move.
    for _ in range(7):
        assert await q.get() is a, "peek rotated the queue"
    assert await q.size() == 3

    # The sender handled A (ack): delete A specifically; B is next, nothing lost or duplicated.
    await q.delete(a)
    assert await q.get() is b and await q.size() == 2

    # A new command arrives while B is in flight, then B finishes: C must still be queued, in order.
    d = {"n": "D"}
    await q.put(d)
    await q.delete(b)
    assert [await q.get(), await q.size()] == [c, 2]
    await q.delete(c); await q.delete(d)
    assert await q.get() is None and await q.delete() is None

    # Deleting something already gone (e.g. dropped after retries) must not remove another command.
    e = {"n": "E"}
    await q.put(e)
    assert await q.delete(a) is None and await q.size() == 1
    print("OK: queue is FIFO, peek does not rotate, delete is by identity")

asyncio.run(main())
