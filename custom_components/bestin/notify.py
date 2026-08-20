"""사용자 알림 — Persistent notifications for gateway outages.

단지 중앙 서버가 내려가면 지금까지는 HA 로그에 'Error setting up entry' 한 줄만
남았습니다. 로그를 열어보지 않는 이상 왜 모든 엔티티가 사라졌는지 알 수 없어서,
같은 내용을 HA 알림으로도 띄웁니다. 알림 ID 는 항목(entry)마다 고정이라 재시도
할 때마다 알림이 쌓이지 않고, 복구되면 자동으로 사라집니다.

Until v1.4.12 a central-server outage produced one line in the HA log and
nothing else: every entity simply went away. These helpers raise the same
information as a persistent notification. The notification id is stable per
config entry, so repeated retries update a single notification instead of
stacking, and it is dismissed automatically once the server answers again.
"""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LOGGER


def _notification_id(entry: ConfigEntry) -> str:
    """항목별 고정 알림 ID — Stable notification id for one config entry."""
    return f"{DOMAIN}_unavailable_{entry.entry_id}"


def async_notify_unavailable(
    hass: HomeAssistant,
    entry: ConfigEntry,
    detail: str,
    *,
    retry_minutes: int | None = None,
) -> None:
    """서버 접속 실패 알림 — Tell the user the server cannot be reached."""
    if retry_minutes is None:
        retry_line = (
            "\n\n연결이 복구되면 이 알림은 자동으로 사라집니다.\n"
            "This notification clears itself once the connection recovers."
        )
    else:
        retry_line = (
            f"\n\n{retry_minutes}분마다 자동으로 다시 시도합니다. 연결이 복구되면 "
            "이 알림은 자동으로 사라집니다.\n"
            f"Retrying automatically every {retry_minutes} minutes; this "
            "notification clears itself once the connection recovers."
        )
    persistent_notification.async_create(
        hass,
        title="BESTIN — 단지 서버 연결 실패 / Central server unreachable",
        message=(
            "iPark 스마트홈 서버에 연결할 수 없습니다. 단지 서버가 점검 중이거나 "
            "다운된 경우 휴대폰 앱에서도 '알림 호출에 실패했습니다' 가 표시됩니다.\n"
            "Cannot reach the iPark Smarthome complex server. When the server "
            "itself is down the phone app fails the same way.\n\n"
            f"상세 / Detail: {detail}"
            f"{retry_line}"
        ),
        notification_id=_notification_id(entry),
    )


def async_notify_auth_failed(
    hass: HomeAssistant, entry: ConfigEntry, detail: str
) -> None:
    """자격 증명 거부 알림 — Tell the user their credentials were rejected."""
    persistent_notification.async_create(
        hass,
        title="BESTIN — 로그인 실패 / Login rejected",
        message=(
            "iPark 스마트홈 서버가 아이디 또는 비밀번호를 거부했습니다. "
            "재시도로는 복구되지 않으니 설정 → 기기 및 서비스 → BESTIN 에서 "
            "다시 설정해 주세요.\n"
            "The iPark Smarthome server rejected the stored username or "
            "password. Retrying will not help — re-add the integration under "
            "Settings → Devices & services → BESTIN.\n\n"
            f"상세 / Detail: {detail}"
        ),
        notification_id=_notification_id(entry),
    )


def async_clear_unavailable(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """알림 해제 — Dismiss the outage notification after a recovery."""
    persistent_notification.async_dismiss(hass, _notification_id(entry))
    LOGGER.debug("Dismissed outage notification for entry %s", entry.entry_id)
