"""문제 신고와 진단 도우미 / Problem report and diagnostics helpers.

설정 > 기기 및 서비스 > BESTIN > 구성 > '문제 신고' 메뉴와 진단 다운로드가
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
        if isinstance(obj, dict):
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
        if isinstance(value, dict):
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


class LogRing(logging.Handler):
    """최근 로그를 메모리에만 보관합니다 / Keeps recent log records in memory.

    로거 수준과 상관없이 통합이 남기는 경고와 오류 (기본 HA 설정에서 보이는
    것) 를 담습니다. 디버그 로그를 켜 두었다면 그것도 담깁니다.

    Holds what the integration logs at the level the logger is set to
    (warnings and errors on a default HA install, debug when enabled).
    """

    def __init__(self, maxlen: int = 200) -> None:
        super().__init__(logging.DEBUG)
        self.records: deque[dict[str, str]] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 / a bad format string must not raise
            message = str(record.msg)
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            message += f" [{type(exc).__name__}: {exc}]"
        self.records.append(
            {
                "time": datetime.fromtimestamp(record.created).isoformat(timespec="seconds"),
                "level": record.levelname,
                "message": message[:600],
            }
        )


LOG_RING = LogRing()


def install_log_ring(logger: logging.Logger) -> None:
    """``LOG_RING`` 을 한 번만 붙입니다 / Attach ``LOG_RING`` once."""
    if LOG_RING not in logger.handlers:
        logger.addHandler(LOG_RING)


# ----------------------------------------------------------------------
# 요약 / Summary
# ----------------------------------------------------------------------


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return "\n".join(lines)


def build_summary_blocks(snapshot: dict[str, Any]) -> list[str]:
    """이미 가린 진단 데이터로 Markdown 요약 블록을 만듭니다.

    중요한 것부터 순서대로 돌려줍니다. 링크가 너무 길면 뒤에서부터 버립니다.

    Build Markdown summary blocks from an already-scrubbed diagnostics
    snapshot, most important first. When the link is too long, blocks are
    dropped from the end.
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
    if kind == "iparkapp":
        status = gw.get("status") or {}
        rows = [
            [
                key,
                st.get("result"),
                st.get("rows"),
                "yes" if st.get("ever_ok") else "no",
                st.get("fail_streak") or "",
                "yes" if st.get("backed_off") else "",
                st.get("at", "")[11:19],
            ]
            for key, st in sorted(status.items())
        ]
        if rows:
            blocks.append(
                "**장치별 마지막 응답 / Last reply per device**\n\n"
                + _table(["device", "result", "rows", "ever ok", "fails", "backed off", "time"], rows)
            )
        if gw.get("login"):
            blocks.append(f"**로그인 / Login:** `{gw['login']}`")
        samples = gw.get("last_bad_reply") or {}
        if samples:
            text = "\n".join(f"{key}: {val[:300]}" for key, val in sorted(samples.items())[:4])
            blocks.append("**실패 응답 예시 / Failed reply samples**\n```\n" + text + "\n```")
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
            blocks.append(
                "**패킷 종류 / Packet types**\n\n"
                + _table(["header/len/cmd", "seen", "bad checksum", "handled", "ignored"], rows)
            )
    elif kind == "center":
        feats = ", ".join(f"{f.get('name')}×{f.get('quantity')}" for f in gw.get("features") or [])
        blocks.append(
            f"**Center:** `{gw.get('version')}`, features: {feats or '-'}, "
            f"elevators `{gw.get('elevator_number')}`, slots `{gw.get('elevator_slots')}`"
        )
        msgs = gw.get("elevator_messages") or []
        if msgs:
            text = "\n".join(str(m)[:200] for m in msgs[-6:])
            blocks.append("**엘리베이터 메시지 / Elevator messages**\n```\n" + text + "\n```")

    log = snapshot.get("log") or []
    if log:
        text = "\n".join(
            f"{r.get('time', '')[11:19]} {r.get('level', '')[:4]} {r.get('message', '')[:200]}"
            for r in log[-10:]
        )
        blocks.append("**최근 로그 / Recent log**\n```\n" + text + "\n```")

    events = gw.get("events") or []
    if events:
        text = "\n".join(
            " ".join(f"{k}={v}" for k, v in ev.items() if v not in (None, ""))[:200]
            for ev in events[-10:]
        )
        blocks.append("**최근 요청 / Recent requests**\n```\n" + text + "\n```")
    return blocks


_ATTACH_NOTE = (
    "_전체 진단 파일: 설정 > 기기 및 서비스 > BESTIN > ⋮ > 진단 다운로드 후 이 칸에 "
    "끌어다 놓아 주세요. / Full diagnostics: Settings > Devices & services > "
    "BESTIN > ⋮ > Download diagnostics, then drag the file here._"
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

    Over budget, summary blocks go first (from the end); only then is the
    user's own text cut.
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

    kept = list(blocks)
    body = compose(user_text, kept)
    while kept and len(_issue_url(title, body)) > budget:
        kept.pop()
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
