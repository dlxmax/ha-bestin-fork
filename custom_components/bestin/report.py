"""문제 신고와 진단 도우미 / Problem report and diagnostics helpers.

설정 > 기기 및 서비스 > BESTIN > ⚙ (톱니바퀴) > '문제 신고' 메뉴와 진단 다운로드가
같은 요약을 씁니다. 통합은 아무것도 전송하지 않습니다. 사용자가 링크를 열어
GitHub 에서 직접 확인하고 제출합니다.

The options-flow "Report a problem" menu and the diagnostics download share
the summary built here. The integration sends nothing: the user opens the
link, reviews the text on GitHub and submits it themselves.

Home Assistant 를 가져오지 않아 테스트에서 그대로 불러올 수 있습니다.
No Home Assistant imports, so the tests can load this module as is.
"""

from __future__ import annotations

import logging
import re
import traceback
from collections import deque
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import quote

ISSUE_NEW_URL = "https://github.com/dlxmax/ha-bestin-fork/issues/new"
# GitHub 는 한도를 공개하지 않습니다. 너무 길면 414 가 납니다. 한글은 글자당
# 9바이트로 인코딩되므로 넉넉하게 잡습니다.
# GitHub doesn't publish its limit; too long gives a 414. Korean encodes to
# 9 bytes per character, so the budget leaves room.
URL_BUDGET = 7000
REDACTED = "**REDACTED**"
# hass.data 키: 항목별 마지막 설정 실패 / hass.data key: last setup failure per entry.
SETUP_ERRORS_KEY = "bestin_setup_errors"
# hass.data 키: 설정에 실패한 허브의 마지막 게이트웨이 상태.
# hass.data key: gateway state of the hub whose setup last failed.
FAILED_GATEWAY_KEY = "bestin_failed_gateway"
# 통합 로거 이름 / The integration's logger name ("custom_components.bestin").
_PACKAGE = __package__ or "custom_components.bestin"

# 값 전체를 가리는 키 / Keys whose whole value is hidden.
TO_REDACT: set[str] = {
    "password",
    "username",
    "iparkapp_password",
    "iparkapp_username",
    "host",
    "ip",
    "ip_address",
    "uuid",
    "session",
    "lat",
    "lng",
    "access-token",
    "refresh-token",
    "PHPSESSID",
    "user_id",
    "user_name",
    "unique_id",
    "title",
    "url",
}

_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
# 월패드 응답의 세대 정보와 월패드 IP / Household and wallpad IP in replies.
_XML_ATTR_RE = re.compile(r'\b(sender|address)=(["\'])[^"\']*\2')
_HOUSEHOLD_RE = re.compile(r"\d+\s*동\s*\d+\s*호")
_SECRET_PARAM_RE = re.compile(
    r"(login_pwd|login_ide|PHPSESSID|access-token|refresh-token|Authorization|user_id|user_name)"
    r"(['\"]?\s*[=:]\s*['\"]?)[^&\s'\",;}]+",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------
# 가리기 / Redaction
# ----------------------------------------------------------------------


def collect_secrets(*sources: Any) -> list[str]:
    """``TO_REDACT`` 키 아래의 문자열 값을 모읍니다.

    키로 가리는 것만으로는 다른 문자열 안에 들어간 값 (예: 항목 제목의
    사용자명, 오류 메시지 속 IP) 을 놓칩니다. 그래서 실제 값을 모아
    모든 문자열에서 바꿉니다.

    Collect the string values found under ``TO_REDACT`` keys. Key-based
    redaction misses the same value inside other strings (the username in an
    entry title, an IP inside an error message), so every string is also
    searched for these values.
    """
    found: set[str] = set()

    def walk(obj: Any, hidden: bool) -> None:
        # entry.data 는 dict 가 아닌 읽기 전용 Mapping 입니다 (v1.4.23 은 이를
        # 놓쳐 비밀번호와 호스트를 다른 문자열에서 가리지 못했습니다).
        # entry.data is a read-only Mapping, not a dict; v1.4.23 missed that
        # and so never searched other strings for the password or host.
        if isinstance(obj, Mapping):
            for key, val in obj.items():
                walk(val, hidden or str(key) in TO_REDACT)
        elif isinstance(obj, (list, tuple, set)):
            for val in obj:
                walk(val, hidden)
        elif hidden and obj is not None and not isinstance(obj, bool):
            text = str(obj).strip()
            if len(text) >= 3:
                found.add(text)
                # 'iparkapp:<ip>:<user>' 같은 unique_id 의 조각도 포함
                # Parts of composite ids such as 'iparkapp:<ip>:<user>'.
                for part in re.split(r"[:|]", text):
                    if len(part) >= 3 and part != "iparkapp":
                        found.add(part)

    for source in sources:
        walk(source, False)
    # 긴 값부터 바꿔야 짧은 값이 긴 값의 일부만 지우지 않습니다.
    # Longest first, so a short value can't half-replace a longer one.
    return sorted(found, key=len, reverse=True)


def scrub_text(text: Any, secrets: Iterable[str] = ()) -> str:
    """문자열에서 비밀 값, 세대 정보, IP 를 지웁니다 / Scrub one string."""
    out = str(text)
    for secret in secrets:
        if secret:
            out = out.replace(secret, REDACTED)
    out = _SECRET_PARAM_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", out)
    out = _XML_ATTR_RE.sub(lambda m: f"{m.group(1)}={m.group(2)}{REDACTED}{m.group(2)}", out)
    out = _HOUSEHOLD_RE.sub("***동 ***호", out)
    out = _IPV4_RE.sub("x.x.x.x", out)
    return out


def scrub_obj(obj: Any, secrets: Iterable[str] = ()) -> Any:
    """키 가리기와 문자열 정리를 재귀로 적용하고 JSON 으로 쓸 수 있게 바꿉니다.

    Apply key redaction and string scrubbing recursively, and turn the result
    into plain JSON types (sets, tuples, datetimes, non-string keys).
    """
    secrets = list(secrets)

    def walk(value: Any) -> Any:
        if isinstance(value, Mapping):
            result = {}
            for key, val in value.items():
                skey = key if isinstance(key, str) else ":".join(map(str, key)) if isinstance(key, tuple) else str(key)
                if skey in TO_REDACT and val not in (None, ""):
                    result[scrub_text(skey, secrets)] = REDACTED
                else:
                    result[scrub_text(skey, secrets)] = walk(val)
            return result
        if isinstance(value, (list, tuple, deque)):
            return [walk(v) for v in value]
        if isinstance(value, set):
            return sorted((walk(v) for v in value), key=str)
        if isinstance(value, datetime):
            return value.isoformat(timespec="seconds")
        if isinstance(value, (bytes, bytearray)):
            return value.hex()
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return scrub_text(value, secrets)

    return walk(obj)


# ----------------------------------------------------------------------
# 로그 기록 / Recent log records
# ----------------------------------------------------------------------


def _bestin_frames(tb: Any, limit: int = 3) -> str:
    """traceback 중 BESTIN 파일의 마지막 줄들 / Last traceback frames in BESTIN files."""
    try:
        frames = [
            frame
            for frame in traceback.extract_tb(tb)
            if "/bestin/" in frame.filename.replace("\\", "/")
        ][-limit:]
    except Exception:  # noqa: BLE001
        return ""
    return " < ".join(
        f"{frame.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{frame.lineno} {frame.name}"
        for frame in reversed(frames)
    )


def _record_entry(record: logging.LogRecord) -> dict[str, str]:
    try:
        message = record.getMessage()
    except Exception:  # noqa: BLE001 / a bad format string must not raise
        message = str(record.msg)
    if record.exc_info and record.exc_info[1] is not None:
        exc = record.exc_info[1]
        message += f" [{type(exc).__name__}: {exc}]"
        where = _bestin_frames(exc.__traceback__)
        if where:
            message += f" at {where}"
    entry = {
        "time": datetime.fromtimestamp(record.created).isoformat(timespec="seconds"),
        "level": record.levelname,
        "message": message[:600],
    }
    if not record.name.startswith(_PACKAGE):
        entry["logger"] = record.name
    return entry


# 로그 줄이 어느 연결 방식의 것인지 / Which gateway a log line belongs to.
# 모든 모듈이 같은 로거를 쓰므로 파일 이름으로 나눠요. 여기 없는 파일은
# 공통 (shared) 이에요. All modules share one logger, so lines are sorted by
# source file; anything not listed is shared.
_MODULE_KIND = {
    "controller": "rs485",
    "iparkapp": "iparkapp",
    "iparkapp_const": "iparkapp",
    "center": "center",
}
# hub.py 의 RS-485 쪽 함수 (ConnectionManager 와 게이트웨이 감지).
# The RS-485 side of hub.py: ConnectionManager and gateway detection.
_HUB_RS485_FUNCS = frozenset({
    "_is_supported_packet_header", "_parse_conn_str", "connect",
    "_connect_serial", "_connect_socket", "is_connected", "_close_writer",
    "reconnect", "send", "receive", "_receive_socket", "close",
    "determine_gateway_mode",
})
# 패킷마다 남는 디버그 줄. controller 의 ``recent_packets`` 가 이미 최근 50개를
# 보관하므로 로그 버퍼에는 넣지 않아요. A debug line per packet; the
# controller's ``recent_packets`` already keeps the last 50.
_SKIP_DEBUG_PREFIXES = ("Packet viewer - Data:",)
# 같은 줄이 최근 몇 줄 안에 또 오면 개수만 늘려요 / How far back a repeat
# is folded into the earlier line.
_REPEAT_LOOKBACK = 3


def log_kind(record: logging.LogRecord) -> str:
    """기록의 연결 방식 / The gateway kind of a log record."""
    if record.module == "hub" and record.funcName in _HUB_RS485_FUNCS:
        return "rs485"
    return _MODULE_KIND.get(record.module, "shared")


class LogRing(logging.Handler):
    """최근 로그를 메모리에만 보관합니다 / Keeps recent log records in memory.

    연결 방식 (rs485, iparkapp, center, shared) 마다 버퍼가 따로 있어요.
    RS-485 항목이 1초마다 남기는 디버그 줄이 같은 HA 의 iPark 항목 로그를
    밀어내던 문제 때문이에요 (#3). 각 방식마다 ``log`` 는 로거 수준이 허용하는
    모든 줄을, ``warnings`` 는 경고와 오류만 담아서 디버그 줄이 원인이 된
    경고를 밀어내지 못해요. 바로 앞 몇 줄과 같은 줄은 ``count`` 만 늘려요.
    모두 크기가 고정이에요.

    One buffer per gateway kind (rs485, iparkapp, center, shared), because an
    RS-485 entry's once-a-second debug lines pushed every line of an iPark
    entry on the same HA out of the shared buffer (#3). Per kind, ``log``
    holds whatever the logger level lets through and ``warnings`` keeps
    warnings and errors, so a debug flood can't push out the warning that
    mattered. A line identical to one of the last few only bumps its
    ``count``. All fixed size.
    """

    def __init__(self, maxlen: int = 200, warn_maxlen: int = 50) -> None:
        super().__init__(logging.DEBUG)
        self.maxlen = maxlen
        self.warn_maxlen = warn_maxlen
        self.logs: dict[str, deque[dict[str, Any]]] = {}
        self.warns: dict[str, deque[dict[str, Any]]] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if (
            record.levelno < logging.WARNING
            and isinstance(record.msg, str)
            and record.msg.startswith(_SKIP_DEBUG_PREFIXES)
        ):
            return
        entry = _record_entry(record)
        kind = log_kind(record)
        self._add(self.logs.setdefault(kind, deque(maxlen=self.maxlen)), entry)
        if record.levelno >= logging.WARNING:
            self._add(
                self.warns.setdefault(kind, deque(maxlen=self.warn_maxlen)),
                dict(entry),
            )

    @staticmethod
    def _add(ring: deque[dict[str, Any]], entry: dict[str, Any]) -> None:
        for back, prev in enumerate(reversed(ring)):
            if back >= _REPEAT_LOOKBACK:
                break
            if all(prev.get(k) == entry.get(k) for k in ("level", "message", "logger")):
                prev["count"] = prev.get("count", 1) + 1
                prev["last"] = entry["time"]
                return
        ring.append(entry)

    def lines(self, kind: str | None = None, *, warnings: bool = False) -> list[dict[str, Any]]:
        """한 연결 방식과 공통 줄을 시간 순으로 / One kind's lines plus shared ones, by time.

        ``kind`` 가 없으면 모든 방식이에요 / ``None`` means every kind.
        """
        store = self.warns if warnings else self.logs
        kinds = list(store) if kind is None else [kind, "shared"]
        out = [entry for k in dict.fromkeys(kinds) for entry in store.get(k, ())]
        return sorted(out, key=lambda entry: entry["time"])

    @property
    def records(self) -> list[dict[str, Any]]:
        return self.lines()

    @property
    def warnings(self) -> list[dict[str, Any]]:
        return self.lines(warnings=True)


class _ForeignErrors(logging.Handler):
    """다른 로거가 남긴 BESTIN 오류 / BESTIN errors logged by other loggers.

    엔티티 서비스 호출이나 HA 작업 안에서 BESTIN 코드가 예외를 던지면 HA 가
    자기 로거 (``homeassistant.helpers.entity`` 등) 로 남깁니다. 루트 로거에서
    오류 수준이고 traceback 에 BESTIN 파일이 있는 기록만 ``LOG_RING`` 에
    넣습니다. 통합 로거의 기록은 이미 담았으므로 건너뜁니다.

    When BESTIN code raises inside an entity service call or an HA task, HA
    logs it under its own logger. On the root logger, this keeps only
    error-level records whose traceback runs through a BESTIN file. Records
    from the integration's own logger are already captured and skipped.
    """

    def __init__(self, ring: LogRing) -> None:
        super().__init__(logging.ERROR)
        self.ring = ring

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(_PACKAGE):
            return
        exc = record.exc_info[1] if record.exc_info else None
        if exc is None or not _bestin_frames(exc.__traceback__, limit=1):
            return
        self.ring.emit(record)


LOG_RING = LogRing()
_FOREIGN_ERRORS = _ForeignErrors(LOG_RING)


def install_log_ring(logger: logging.Logger) -> None:
    """``LOG_RING`` 을 한 번만 붙입니다 / Attach ``LOG_RING`` once."""
    if LOG_RING not in logger.handlers:
        logger.addHandler(LOG_RING)
    root = logging.getLogger()
    if _FOREIGN_ERRORS not in root.handlers:
        root.addHandler(_FOREIGN_ERRORS)


def gateway_snapshot(hub: Any) -> dict[str, Any]:
    """허브의 게이트웨이 상태 (가리기 전) / Gateway state of a hub, not yet scrubbed."""
    api = getattr(hub, "api", None)
    snapshot: dict[str, Any] = {}
    if api is not None and hasattr(api, "diagnostics_snapshot"):
        try:
            snapshot = api.diagnostics_snapshot()
        except Exception as ex:  # noqa: BLE001 / diagnostics must never fail
            snapshot = {"snapshot_error": f"{type(ex).__name__}: {ex}"}
    connection = getattr(hub, "connection", None)
    if connection is not None:
        snapshot.setdefault("kind", "rs485")
        snapshot["hub_gateway_mode"] = getattr(hub, "gateway_mode", None)
        try:
            snapshot.setdefault("connected", connection.is_connected())
        except Exception:  # noqa: BLE001
            pass
        snapshot.setdefault("reconnect_attempts", getattr(connection, "reconnect_attempts", None))
    return snapshot


# ----------------------------------------------------------------------
# 요약 / Summary
# ----------------------------------------------------------------------


class Block(str):
    """요약 블록과 버리는 순서 / A summary block and when it gets dropped.

    링크가 너무 길면 drop 값이 큰 블록부터 버립니다. 일반 문자열은 0 이고,
    같은 값끼리는 뒤에 있는 것부터 버립니다.
    When the link is too long, blocks with a higher ``drop`` go first. Plain
    strings count as 0; among equals the later block goes first.
    """

    drop: int = 0

    def __new__(cls, text: str, drop: int = 0) -> "Block":
        obj = super().__new__(cls, text)
        obj.drop = drop
        return obj


# 버리는 순서 / Drop order: request history first, warnings and the device
# table last.
_DROP_TABLE = 1
_DROP_WARNINGS = 2
_DROP_LOGIN = 3
_DROP_LOG = 4
_DROP_SAMPLES = 5
_DROP_EVENTS = 6


def _room_span(rooms: list[int]) -> str:
    """[1, 2, 3, 5] -> "1-3,5"."""
    parts: list[str] = []
    start = prev = rooms[0]
    for room in rooms[1:] + [None]:
        if room is not None and room == prev + 1:
            prev = room
            continue
        parts.append(f"{start}-{prev}" if prev != start else str(start))
        if room is not None:
            start = prev = room
    return ",".join(parts)


def _status_rows(status: dict[str, Any]) -> list[list[Any]]:
    """방마다 같은 결과는 한 줄로 묶습니다 / Rooms with the same result share a row.

    예: light:1 부터 light:6 까지 모두 empty 면 "light:1-6" 한 줄입니다.
    For example light:1 to light:6 all empty becomes one "light:1-6" row.
    """
    groups: dict[tuple, dict[str, Any]] = {}
    for key, st in sorted(status.items()):
        cls, _, room = key.partition(":")
        values = (
            st.get("result"),
            st.get("rows"),
            "yes" if st.get("ever_ok") else "no",
            st.get("fail_streak") or "",
            "yes" if st.get("backed_off") else "",
        )
        group = groups.setdefault((cls, room.isdigit(), values), {"rooms": [], "keys": [], "at": ""})
        group["keys"].append(key)
        if room.isdigit():
            group["rooms"].append(int(room))
        group["at"] = max(group["at"], str(st.get("at", "")))
    rows = []
    for (cls, numbered, values), group in groups.items():
        if numbered and len(group["rooms"]) > 1:
            names = [f"{cls}:{_room_span(sorted(group['rooms']))}"]
        else:
            names = group["keys"]
        for name in names:
            rows.append([name, *values, group["at"][11:19]])
    return sorted(rows, key=lambda row: row[0])


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return "\n".join(lines)


def build_summary_blocks(snapshot: dict[str, Any]) -> list[str]:
    """이미 가린 진단 데이터로 Markdown 요약 블록을 만듭니다.

    보여줄 순서대로 돌려줍니다. 링크가 너무 길면 Block.drop 이 큰 것부터 버립니다.

    Build Markdown summary blocks from an already-scrubbed diagnostics
    snapshot, in display order. When the link is too long, blocks with the
    highest Block.drop are left out first.
    """
    info = snapshot.get("integration", {})
    blocks: list[str] = []

    head = [
        f"- BESTIN: `{info.get('version')}`",
        f"- Home Assistant: `{info.get('ha_version')}`",
        f"- 연결 방식 / Gateway: `{info.get('gateway')}`",
    ]
    if info.get("site"):
        head.append(f"- 단지 / Site: `{info['site']}`")
    if info.get("entry_state"):
        head.append(f"- 항목 상태 / Entry state: `{info['entry_state']}`")
    if snapshot.get("setup_error"):
        head.append(f"- 설정 오류 / Setup error: `{snapshot['setup_error']}`")
    blocks.append("\n".join(head))

    entities = snapshot.get("entities") or {}
    if entities:
        parts = [
            f"{domain} {counts.get('total', 0)}"
            + (f" ({counts['unavailable']} unavailable)" if counts.get("unavailable") else "")
            for domain, counts in sorted(entities.items())
        ]
        blocks.append("**엔티티 / Entities:** " + ", ".join(parts))
    else:
        blocks.append("**엔티티 / Entities:** 없음 / none")

    gw = snapshot.get("gateway") or {}
    kind = gw.get("kind")
    if gw.get("from_failed_setup"):
        blocks.append(
            f"_아래 상태는 실패한 설정 시도 ({gw.get('saved_at', '?')}) 에서 가져왔어요. / "
            f"The state below is from the failed setup attempt at {gw.get('saved_at', '?')}._"
        )
    if kind == "iparkapp":
        rows = _status_rows(gw.get("status") or {})
        if rows:
            blocks.append(Block(
                "**장치별 마지막 응답 / Last reply per device**\n\n"
                + _table(["device", "result", "rows", "ever ok", "fails", "backed off", "time"], rows),
                _DROP_TABLE,
            ))
        if gw.get("login"):
            blocks.append(Block(f"**로그인 / Login:** `{gw['login']}`", _DROP_LOGIN))
        samples = gw.get("last_bad_reply") or {}
        if samples:
            text = "\n".join(f"{key}: {val[:300]}" for key, val in sorted(samples.items())[:4])
            blocks.append(Block("**실패 응답 예시 / Failed reply samples**\n```\n" + text + "\n```", _DROP_SAMPLES))
    elif kind == "rs485":
        blocks.append(
            f"**RS-485:** mode `{gw.get('gateway_type')}`, rooms `{gw.get('room_to_command')}`, "
            f"connected `{gw.get('connected')}`, reconnects `{gw.get('reconnect_attempts')}`, "
            f"packets `{gw.get('packets_total')}`"
        )
        types = gw.get("packet_types") or {}
        rows = [
            [key, c.get("seen"), c.get("bad_checksum"), c.get("handled"), c.get("ignored")]
            for key, c in sorted(types.items(), key=lambda kv: -kv[1].get("seen", 0))[:15]
        ]
        if rows:
            blocks.append(Block(
                "**패킷 종류 / Packet types**\n\n"
                + _table(["header/len/cmd", "seen", "bad checksum", "handled", "ignored"], rows),
                _DROP_TABLE,
            ))
    elif kind == "center":
        feats = ", ".join(f"{f.get('name')}×{f.get('quantity')}" for f in gw.get("features") or [])
        blocks.append(
            f"**Center:** `{gw.get('version')}`, features: {feats or '-'}, "
            f"elevators `{gw.get('elevator_number')}`, slots `{gw.get('elevator_slots')}`"
        )
        msgs = gw.get("elevator_messages") or []
        if msgs:
            text = "\n".join(str(m)[:200] for m in msgs[-6:])
            blocks.append(Block("**엘리베이터 메시지 / Elevator messages**\n```\n" + text + "\n```", _DROP_TABLE))

    def log_lines(records: list[dict[str, str]]) -> str:
        return "\n".join(
            f"{r.get('time', '')[5:19].replace('T', ' ')} {r.get('level', '')[:4]} "
            + (f"[{r['logger']}] " if r.get("logger") else "")
            + r.get("message", "")[:240]
            + (f" (×{r['count']}, last {str(r.get('last', ''))[11:19]})" if r.get("count", 1) > 1 else "")
            for r in records
        )

    warnings = snapshot.get("warnings") or []
    if warnings:
        blocks.append(Block(
            "**최근 경고와 오류 / Recent warnings and errors**\n```\n"
            + log_lines(warnings[-8:])
            + "\n```",
            _DROP_WARNINGS,
        ))
    # 경고 블록에 이미 있는 줄은 빼고 보여줍니다 / Skip lines already shown above.
    shown = {(r.get("time"), r.get("message")) for r in warnings[-8:]}
    log = [r for r in snapshot.get("log") or [] if (r.get("time"), r.get("message")) not in shown]
    if log:
        blocks.append(Block("**최근 로그 / Recent log**\n```\n" + log_lines(log[-10:]) + "\n```", _DROP_LOG))

    events = gw.get("events") or []
    if events:
        text = "\n".join(
            " ".join(f"{k}={v}" for k, v in ev.items() if v not in (None, ""))[:200]
            for ev in events[-10:]
        )
        blocks.append(Block("**최근 요청 / Recent requests**\n```\n" + text + "\n```", _DROP_EVENTS))
    return blocks


_ATTACH_NOTE = (
    "_전체 진단 파일: 설정 > 기기 및 서비스 > BESTIN > ⋮ (점 세 개) > 진단 다운로드 후 이 칸에 "
    "끌어다 놓아 주세요. / Full diagnostics: Settings > Devices & services > "
    "BESTIN > ⋮ (three dots) > Download diagnostics, then drag the file here._"
)


def _issue_url(title: str, body: str) -> str:
    return f"{ISSUE_NEW_URL}?title={quote(title)}&body={quote(body)}"


def build_issue_url(
    title: str,
    user_text: str,
    blocks: list[str],
    budget: int = URL_BUDGET,
    attach_note: bool = True,
) -> tuple[str, str]:
    """GitHub 새 이슈 링크와 본문을 만듭니다 / Build the new-issue link and body.

    길이를 넘으면 요약 블록을 뒤에서부터 버리고, 그래도 넘으면 사용자 글을
    자릅니다. 사용자 글보다 요약을 먼저 줄입니다.

    Over budget, summary blocks go first (highest ``Block.drop`` first, then
    from the end); only then is the user's own text cut.
    """
    user_text = (user_text or "").strip() or "(GitHub 에서 작성 / to be written on GitHub)"

    def compose(text: str, kept: list[str]) -> str:
        parts = [
            "### 무엇이 안 되나요? / What is not working?",
            text,
            "### 자동 요약 / Automatic summary",
            *kept,
        ]
        if len(kept) < len(blocks):
            parts.append(f"_(요약 {len(blocks) - len(kept)}개 생략 / {len(blocks) - len(kept)} summary block(s) left out)_")
        if attach_note:
            parts.append(_ATTACH_NOTE)
        return "\n\n".join(parts)

    order = sorted(
        range(len(blocks)),
        key=lambda i: (getattr(blocks[i], "drop", 0), i),
        reverse=True,
    )
    dropped: set[int] = set()
    kept = list(blocks)
    body = compose(user_text, kept)
    for index in order:
        if len(_issue_url(title, body)) <= budget:
            break
        dropped.add(index)
        kept = [b for i, b in enumerate(blocks) if i not in dropped]
        body = compose(user_text, kept)
    cut = user_text
    while len(_issue_url(title, body)) > budget and len(cut) > 20:
        cut = cut[: int(len(cut) * 0.8)]
        body = compose(cut + " …(잘림 / truncated)", kept)
    return _issue_url(title, body), body


def issue_title(gateway: str | None, version: str | None, user_text: str = "") -> str:
    first = (user_text or "").strip().splitlines()[0][:60] if (user_text or "").strip() else ""
    title = f"[문제 신고 / Report] {gateway or '?'} v{version or '?'}"
    return f"{title}: {first}" if first else title


def flow_error_blocks(
    step: str,
    exc: BaseException,
    version: str | None,
    ha_version: str | None,
    secrets: Iterable[str] = (),
) -> list[str]:
    """설정 단계 오류용 요약 (항목이 아직 없음) / Summary for a config-flow error.

    BESTIN 파일 안의 traceback 줄만 담습니다. 코드 줄이라 비밀 값이 없습니다.
    Only traceback frames inside BESTIN files: code lines, no user data.
    """
    secrets = list(secrets)
    frames = [
        frame
        for frame in traceback.extract_tb(exc.__traceback__)
        if "/bestin/" in frame.filename.replace("\\", "/")
    ][-6:]
    trace = "\n".join(
        f"{frame.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{frame.lineno} "
        f"{frame.name}: {(frame.line or '').strip()}"
        for frame in frames
    )
    blocks = [
        "\n".join(
            [
                f"- BESTIN: `{version}`",
                f"- Home Assistant: `{ha_version}`",
                f"- 설정 단계 / Setup step: `{step}`",
                f"- 오류 / Error: `{scrub_text(error_text(exc), secrets)}`",
            ]
        )
    ]
    if trace:
        blocks.append("**Traceback (BESTIN)**\n```\n" + scrub_text(trace, secrets) + "\n```")
    return blocks


def error_text(exc: BaseException) -> str:
    message = str(exc)
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
