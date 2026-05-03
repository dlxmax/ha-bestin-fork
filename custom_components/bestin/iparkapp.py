"""iPark 스마트홈 앱 — Client for the new gateway type.

이 모듈은 단지 중앙 서버(예: ``http://220.79.141.134/``)와 통신합니다.
공식 안드로이드 앱(WebView)이 사용하는 URL과 헤더를 그대로 흉내냅니다.
This client talks to the per-complex central PHP server using the same
URL and headers as the official Android app's WebView.

핵심 차이점 — Key differences from existing ``center.py`` v1 path:
  - URL은 ``/webapp/data/...``를 사용합니다 (기존 v1의 ``/mobilehome/data/...`` 아님).
    Uses ``/webapp/data/...`` (not ``/mobilehome/data/...``).
  - ``X-Requested-With: XMLHttpRequest`` 헤더가 반드시 필요합니다.
    Sends ``X-Requested-With: XMLHttpRequest`` (mandatory).
  - 난방은 별도 PHP 핸들러(``getHomeDevice_heat.php``)를 사용합니다.
    Routes thermostat traffic to ``getHomeDevice_heat.php``.
  - 로그인은 2단계입니다: GET 랜딩 → POST 인증.
    Uses the 2-step login: GET landing page → POST credentials.
  - 단지 디렉터리(i-parklife.com) 자동 조회로 IP 입력 부담을 줄입니다.
    Auto-resolves the complex IP via the i-parklife.com directory.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Callable

import aiohttp

from homeassistant.components.climate.const import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    BRAND_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_PLATFORM_MAP,
    LOGGER,
    MAIN_DEVICES,
    PLATFORM_SIGNAL_MAP,
    DeviceInfo,
    DeviceProfile,
)
from .iparkapp_const import (
    AJAX_HEADERS,
    CONF_IPARKAPP_PASSWORD,
    CONF_IPARKAPP_SITE,
    CONF_IPARKAPP_USERNAME,
    DEFAULT_SESSION_REFRESH_MINUTES,
    DEVICE_CLASSES,
    ENERGY_CATEGORIES,
    ENERGY_PATH_TEMPLATE,
    FRIENDLY_DEVICE_NAMES,
    INDEX_PATH,
    LOGIN_DATA_PATH,
    LOGIN_LANDING_PATH,
    REFERER_PAGES,
    RESULT_OK,
    ROOM_PROBE_RANGE,
    USER_AGENT,
    DeviceClass,
    make_unit_id,
    normalize_status,
)


class BestinIparkAppAPI:
    """단지 중앙 서버 클라이언트 — Per-complex central-server client.

    Intentionally mirrors the surface of ``BestinCenterAPI`` so the existing
    ``hub.py`` plumbing and HA entity platforms see the same shape. Only the
    on-the-wire protocol differs.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        entity_groups: dict[str, set[str]],
        hub_id: str,
        add_device_callback: Callable,
    ) -> None:
        """초기화 — Initialise client and HTTP session."""
        self.hass = hass
        self.entry = entry
        self.entity_groups = entity_groups
        self.hub_id = hub_id
        self.add_device_callback = add_device_callback

        site: dict[str, str] = entry.data[CONF_IPARKAPP_SITE]
        self.host: str = site["ip"]
        self.site = site
        self.username: str = entry.data[CONF_IPARKAPP_USERNAME]
        self.password: str = entry.data[CONF_IPARKAPP_PASSWORD]

        self.session: aiohttp.ClientSession = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(),
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )

        self.devices: dict[str, DeviceProfile] = {}
        self.tasks: list[Any] = []
        # 속성 이름은 device.py 의 extra_state_attributes 가 읽는 것과 정확히
        # 일치해야 합니다 — must match exactly what device.py reads in
        # ``extra_state_attributes``, otherwise entities raise AttributeError
        # and HA marks them unavailable.
        self.last_update_time: datetime = datetime.now()
        self.last_sess_refresh: datetime = datetime.now()
        # 객실(room) 디바이스가 실제로 존재하는지 결과 캐시 — Cache of which
        # room-scoped devices actually exist so we don't poll dead rooms.
        self._room_exists: dict[tuple[str, int], bool] = {}
        # status_map 의 unit_cnt 캐시 — Cached <status_map unit_cnt="N"> per
        # device class. For heat, anything beyond ``unit_cnt`` is exposed as a
        # ``heatsource`` sensor rather than as a climate entity. The exact
        # meaning of those extra readings varies by complex and is not
        # confirmed (one speculation is district-heating supply temperature).
        self._unit_cnt: dict[str, int] = {}

    # ------------------------------------------------------------------
    # 라이프사이클 — Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """로그인 후 폴링 스케줄을 시작합니다 — Login then schedule polling."""
        await self._login()
        await self._prime_session()

        poll_interval = timedelta(
            seconds=self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        refresh_interval = timedelta(minutes=DEFAULT_SESSION_REFRESH_MINUTES)

        self.hass.create_task(self._poll_all())
        self.tasks = [
            async_track_time_interval(self.hass, self._scheduled_poll, poll_interval),
            async_track_time_interval(
                self.hass, self._scheduled_refresh, refresh_interval
            ),
        ]
        LOGGER.info(
            "iPark 스마트홈 앱 연동 시작 — Started iParkApp client for %s (%s)",
            self.site.get("sitename", self.host),
            self.host,
        )

    async def stop(self) -> None:
        """모든 작업 중지 — Cancel scheduled tasks and close the HTTP session."""
        for cancel in self.tasks:
            try:
                cancel()
            except Exception:  # pragma: no cover — defensive
                pass
        self.tasks = []
        if not self.session.closed:
            await self.session.close()

    @callback
    async def _scheduled_poll(self, now: datetime) -> None:
        self.last_update_time = now
        try:
            await self._poll_all()
        except Exception as ex:  # noqa: BLE001 — log everything so HA shows it
            LOGGER.exception("폴링 실패 — Polling failed: %s", ex)

    @callback
    async def _scheduled_refresh(self, now: datetime) -> None:
        self.last_sess_refresh = now
        try:
            await self._login()
        except Exception as ex:  # noqa: BLE001
            LOGGER.exception("세션 갱신 실패 — Session refresh failed: %s", ex)

    # ------------------------------------------------------------------
    # 인증 — Authentication
    # ------------------------------------------------------------------

    async def _login(self) -> None:
        """2단계 로그인 — Two-step login (GET landing, then POST credentials)."""
        landing_url = f"http://{self.host}{LOGIN_LANDING_PATH}"
        landing_params = {
            "device": "WA",
            "login_ide": self.username,
            "login_pwd": self.password,
            "SITEWeather": self.site.get("weather", ""),
            "SITELat": self.site.get("lat", ""),
            "SITELng": self.site.get("lng", ""),
        }
        try:
            async with self.session.get(
                landing_url,
                params=landing_params,
                headers={"User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                # PHPSESSID 쿠키가 세션 쿠키 저장소에 자동 저장됩니다.
                # The PHPSESSID cookie lands in the cookie jar automatically.

            data_url = f"http://{self.host}{LOGIN_DATA_PATH}"
            data_body = {
                "device": "WA",
                "login_ide": self.username,
                "login_pwd": self.password,
                "siteweather": self.site.get("weather", ""),
                "sitelat": self.site.get("lat", ""),
                "sitelng": self.site.get("lng", ""),
            }
            async with self.session.post(
                data_url,
                data=data_body,
                headers={"User-Agent": USER_AGENT, **AJAX_HEADERS},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                payload = await resp.json(content_type=None)
                if payload.get("ret") != "success":
                    LOGGER.error(
                        "로그인 실패 — iParkApp login failed: %s", payload
                    )
                    raise RuntimeError(f"iparkapp login failed: {payload}")
                LOGGER.debug("iParkApp login OK: %s", payload)
        except aiohttp.ClientError as ex:
            LOGGER.error("로그인 네트워크 오류 — iParkApp login network error: %s", ex)
            raise

    async def _prime_session(self) -> None:
        """세션 프라이밍 — Touch index.php so the wallpad IPC channel registers."""
        try:
            async with self.session.get(
                f"http://{self.host}{INDEX_PATH}",
                headers={"User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
        except aiohttp.ClientError as ex:
            LOGGER.warning("세션 프라이밍 실패 — Session prime failed: %s", ex)

    # ------------------------------------------------------------------
    # 저수준 요청 — Low-level requests
    # ------------------------------------------------------------------

    async def _request(
        self,
        path: str,
        params: dict[str, str | int],
        *,
        referer_path: str = "/webapp/index.php",
    ) -> str | None:
        """공통 GET 요청 — Authenticated GET with required AJAX headers."""
        url = f"http://{self.host}{path}"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": f"http://{self.host}{referer_path}",
            **AJAX_HEADERS,
        }
        try:
            async with self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                return await resp.text()
        except aiohttp.ClientError as ex:
            LOGGER.warning("요청 실패 — Request failed (%s): %s", path, ex)
            return None

    @staticmethod
    def _parse_xml_result(body: str | None) -> tuple[str | None, ET.Element | None]:
        """``<service result="...">`` 의 result 값과 root 요소를 반환합니다.
        Return the ``result`` attribute and root element from a wallpad XML response."""
        if not body or not body.strip():
            return None, None
        try:
            root = ET.fromstring(body)
        except ET.ParseError as ex:
            LOGGER.debug("XML 파싱 실패 — XML parse failed: %s; body=%r", ex, body[:200])
            return None, None
        service = root.find(".//service")
        if service is None:
            return None, root
        return service.get("result"), root

    # ------------------------------------------------------------------
    # 장치 등록 (center.py 의 패턴을 그대로 따릅니다)
    # Device registration (mirrors center.py's pattern so HA platforms work as-is)
    # ------------------------------------------------------------------

    @staticmethod
    def _short_hash(s: str) -> str:
        """결정적 해시 — Deterministic short hash (mirrors center.py).

        Python's built-in ``hash()`` is randomised per process, which would
        change unique_ids on every HA restart and orphan entities. Use
        sha256-based base64 truncation instead so the suffix is stable.
        """
        digest = hashlib.sha256(s.encode()).digest()
        return base64.urlsafe_b64encode(digest)[:8].decode("utf-8").upper()

    def _initial_device(
        self, device_id: str, sub_id: str | None, state: Any
    ) -> DeviceProfile:
        """장치 프로파일을 초기화/조회합니다 — Get-or-create a DeviceProfile."""
        device_type, device_room = device_id.split("_", 1)
        did_suffix = f"_{sub_id}" if sub_id else ""
        full_device_id = f"{BRAND_PREFIX}_{device_id}{did_suffix}"

        # 친근한 이름 (예: 'livinglight' → 'Light', 'temper' → 'Thermostat')
        # Friendly display name (e.g. 'livinglight' → 'Light').
        friendly = FRIENDLY_DEVICE_NAMES.get(device_type, device_type.title())
        if sub_id:
            sub_id_parts = sub_id.split("_")
            device_name = f"{friendly} {device_room} {' '.join(sub_id_parts)}"
        else:
            device_name = f"{friendly} {device_room}"

        if sub_id and not sub_id.isdigit():
            device_type_lookup = (
                f"{device_type}:{''.join(filter(str.isalpha, sub_id))}"
            )
        else:
            device_type_lookup = device_type

        if device_type_lookup not in MAIN_DEVICES:
            uid_suffix = f"-{self._short_hash(self.hub_id)}"
        else:
            uid_suffix = ""
        unique_id = f"{full_device_id}{uid_suffix}"

        if full_device_id not in self.devices:
            info = DeviceInfo(
                device_type=device_type_lookup,
                name=device_name,
                room=device_room,
                state=state,
                device_id=full_device_id,
            )
            self.devices[full_device_id] = DeviceProfile(
                enqueue_command=self.enqueue_command,
                domain=DEVICE_PLATFORM_MAP.get(
                    device_type_lookup, DEVICE_PLATFORM_MAP.get(device_type, "sensor")
                ),
                unique_id=unique_id,
                info=info,
            )
        return self.devices[full_device_id]

    def _set_device(
        self,
        device_type: str,
        device_number: int,
        unit_id: str | None,
        status: Any,
    ) -> None:
        """장치 상태를 갱신하고 필요시 콜백을 발생시킵니다 — Update device state."""
        if device_type not in DEVICE_PLATFORM_MAP:
            LOGGER.debug("지원되지 않는 장치 유형 — Unsupported device type: %s", device_type)
            return

        device_id = f"{device_type}_{device_number}"
        device = self._initial_device(device_id, unit_id, status)

        if unit_id and not unit_id.isdigit():
            looked_up = (
                f"{device_type}:{''.join(filter(str.isalpha, unit_id))}"
            )
            platform = DEVICE_PLATFORM_MAP.get(
                looked_up, DEVICE_PLATFORM_MAP[device_type]
            )
        else:
            platform = DEVICE_PLATFORM_MAP[device_type]

        if device.unique_id not in self.entity_groups.get(platform, set()):
            signal = PLATFORM_SIGNAL_MAP[platform]
            self.add_device_callback(signal, device)

        if device.info.state != status:
            device.info.state = status
            device.update_callbacks()

    # ------------------------------------------------------------------
    # 장치 클래스별 폴링 — Per-device-class polling
    # ------------------------------------------------------------------

    async def _poll_all(self) -> None:
        """모든 장치 클래스를 동시에 갱신합니다 — Poll every class concurrently."""
        coros: list[Any] = []
        for cls in DEVICE_CLASSES.values():
            if cls.room_scoped:
                for n in ROOM_PROBE_RANGE:
                    if self._room_exists.get((cls.key, n), True):
                        coros.append(self._fetch_class(cls, room=n))
            elif cls.key == "temper":
                # 난방은 객실별 unit_num 으로 처리 — Heat is per-room via unit_num.
                for n in ROOM_PROBE_RANGE:
                    if self._room_exists.get((cls.key, n), True):
                        coros.append(self._fetch_class(cls, room=n))
            else:
                coros.append(self._fetch_class(cls))

        for kind in ENERGY_CATEGORIES:
            coros.append(self._fetch_energy(kind))

        await asyncio.gather(*coros, return_exceptions=True)

    async def _fetch_class(self, cls: DeviceClass, room: int | None = None) -> None:
        """단일 장치 클래스의 상태를 가져옵니다 — Fetch one device class."""
        params: dict[str, str | int] = {
            "req_name": cls.req_name,
            "req_action": "status",
        }
        if cls.unit_pattern is not None and "{n}" not in cls.unit_pattern:
            # static patterns: gas1 / ventil / null
            params["req_unit_num"] = cls.unit_pattern
        if cls.key == "temper" and room is not None:
            params["req_unit_num"] = make_unit_id(cls, room)
        if cls.room_scoped and room is not None:
            params["req_dev_num"] = room

        body = await self._request(
            cls.path,
            params,
            referer_path=REFERER_PAGES.get(cls.key, "/webapp/index.php"),
        )
        result, root = self._parse_xml_result(body)

        if result != RESULT_OK:
            if room is not None and result is None:
                # 응답이 비어 있다면 해당 객실에는 장치가 없다고 판단합니다.
                # Empty response → assume the room doesn't exist; stop polling it.
                self._room_exists[(cls.key, room)] = False
            LOGGER.debug(
                "%s 응답=%s — fetch %s (room=%s) result=%s",
                cls.key, result, cls.key, room, result,
            )
            return

        # 객실 디바이스가 존재함을 표시 — Mark this room as live.
        if room is not None:
            self._room_exists[(cls.key, room)] = True

        # status_map 의 unit_cnt 를 캐시합니다 — Cache unit_cnt for later use.
        # ``unit_cnt`` 를 넘어서는 'room' 응답은 제어 가능한 방이 아니므로 별도
        # heatsource 센서로 분리합니다 (정확한 의미는 단지마다 상이).
        # Any 'room' returned beyond ``unit_cnt`` isn't a controllable room —
        # we route it to a separate ``heatsource`` sensor; exact meaning varies
        # by complex (we don't claim to know what it is).
        status_map = (root or ET.Element("imap")).find(".//status_map")
        if status_map is not None and status_map.get("unit_cnt"):
            try:
                self._unit_cnt[cls.key] = int(status_map.get("unit_cnt", "0"))
            except ValueError:
                pass

        device_number = room if room is not None else 1
        for info in (root or ET.Element("imap")).findall(".//status_info"):
            unit_num = info.get("unit_num", "")
            unit_status = info.get("unit_status", "")
            self._dispatch_status(cls, device_number, unit_num, unit_status, info)

    def _dispatch_status(
        self,
        cls: DeviceClass,
        device_number: int,
        unit_num: str,
        unit_status: str,
        node: ET.Element,
    ) -> None:
        """``<status_info>`` 한 개를 디바이스 모델에 반영합니다 — Translate one row."""
        # 엔터티 클래스 별칭 — entity-class alias for HA mapping
        alias = {
            "livinglight": "livinglight",
            "light": "light",
            "electric": "electric",
            "temper": "temper",
            "gas": "gas",
            "ventil": "ventil",
            "mode": "mode",
            "doorlock": "doorlock",
        }[cls.key]

        sub_id: str | None = None
        if unit_num.startswith("switch"):
            sub_id = unit_num[len("switch"):]
        elif unit_num == "gas1":
            sub_id = None
        elif unit_num == "ventil":
            sub_id = None
        elif unit_num.startswith("room"):
            sub_id = None
        else:
            sub_id = unit_num or None

        # 기본적으로는 정규화된 boolean/문자열 — Default: normalised value.
        value: Any = normalize_status(unit_status)
        # 난방은 ``mode/setpoint/current`` 형식의 슬래시 문자열입니다.
        # Heat encodes status as ``mode/setpoint/current`` joined with '/'.
        # Climate 엔티티가 읽는 키 (ATTR_HVAC_MODE 등) 와 정확히 일치해야 합니다.
        # Keys must match what the climate entity reads (ATTR_HVAC_MODE etc.)
        # otherwise climate.py raises KeyError → entity becomes unavailable.
        if cls.key == "temper":
            parts = (unit_status or "").split("/")
            mode = parts[0] if parts else ""
            try:
                setpoint = float(parts[1]) if len(parts) > 1 and parts[1] else None
            except ValueError:
                setpoint = None
            try:
                current = float(parts[2]) if len(parts) > 2 and parts[2] else None
            except ValueError:
                current = None
            value = {
                ATTR_HVAC_MODE: HVACMode.HEAT if mode in ("on", "heat") else HVACMode.OFF,
                SERVICE_SET_TEMPERATURE: setpoint,
                ATTR_CURRENT_TEMPERATURE: current,
                # 부가 정보 — auxiliary fields for our own use / debugging
                "raw_mode": mode,
                "raw_status": unit_status,
            }
            # 'unit_cnt' 를 초과하는 방 번호는 제어 불가 — 별도 센서로 분리.
            # 정확한 의미는 단지마다 상이하며 확인되지 않았습니다.
            # Rooms beyond ``status_map.unit_cnt`` aren't controllable
            # thermostats — re-route to a read-only sensor entity. Exact
            # meaning varies by complex; we don't claim to know what the value
            # represents (could be a district-heating supply temp, could be
            # something else entirely).
            unit_cnt = self._unit_cnt.get("temper")
            if unit_cnt and device_number > unit_cnt:
                # current 값이 가장 의미있음 — current temp is the useful value.
                self._set_device(
                    "heatsource", device_number, "supply", current if current is not None else value
                )
                return

        self._set_device(alias, device_number, sub_id, value)

    # ------------------------------------------------------------------
    # 에너지 모니터링 — Energy monitoring
    # ------------------------------------------------------------------

    async def _fetch_energy(self, kind: str) -> None:
        """``getEnergyAvr_monthly_{kind}.php`` 를 가져와 센서로 노출합니다.
        Fetch the monthly-average JSON for ``kind`` and expose two sensors per
        category (my-home and complex-average for the latest month)."""
        now = datetime.now()
        months = []
        for off in (2, 1, 0):
            year = now.year
            month = now.month - off
            while month <= 0:
                year -= 1
                month += 12
            months.append(f"{year:04d}-{month:02d}")

        params = {"eDate": months[0], "eDate2": months[1], "eDate3": months[2]}
        url = ENERGY_PATH_TEMPLATE.format(kind=kind)
        body = await self._request(
            url, params, referer_path="/webapp/energyView.php"
        )
        if not body or not body.strip().startswith("["):
            return
        try:
            payload = json.loads(body)
        except ValueError as ex:
            LOGGER.debug("에너지 JSON 파싱 실패 — Energy JSON parse failed: %s", ex)
            return

        # ENERGY_CATEGORIES[kind] holds bilingual labels — surfaced in docs
        # rather than entity attributes (HA users can rename the sensor).
        for series in payload:
            name = series.get("name", "")
            data = series.get("data", [])
            if not data:
                continue
            last = data[-1]
            try:
                value = float(last)
            except (TypeError, ValueError):
                value = last
            # 시리즈 이름으로 '나의 세대' / '전체 평균' 구분
            # Differentiate "my home" vs "complex average" by series name.
            scope = "mine" if "나의" in name or "my" in name.lower() else "avg"
            sub_id = f"{scope}_{kind.lower()}"
            self._set_device("energy", 1, sub_id, value)

    # ------------------------------------------------------------------
    # 명령 송신 — Command dispatch (called by HA entity platforms)
    # ------------------------------------------------------------------

    @callback
    async def enqueue_command(
        self, device_id: str, value: Any, **kwargs: dict | None
    ) -> None:
        """HA → 월패드 제어 명령 — Translate an HA command into a wallpad request."""
        parts = device_id.split("_")
        device_type = parts[1]
        room_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

        sub_type: str | None = None
        pos_id: int = 0
        if len(parts) > 3:
            if parts[3].isdigit():
                pos_id = int(parts[3])
            else:
                sub_type = parts[3]
        if len(parts) > 4 and parts[4].isdigit():
            pos_id = int(parts[4])
        if kwargs:
            sub_type, value = next(iter(kwargs.items()))

        # 도어락은 제어 불가 — Doorlock is read-only in the app.
        if device_type == "doorlock":
            LOGGER.warning(
                "도어락은 제어할 수 없습니다 — Doorlock control is not supported by the app."
            )
            return

        if device_type not in DEVICE_CLASSES:
            LOGGER.warning(
                "지원되지 않는 장치 유형 — Unsupported device type for control: %s",
                device_type,
            )
            return

        cls = DEVICE_CLASSES[device_type]
        unit_id = (
            f"{sub_type}{pos_id or room_id}"
            if sub_type
            else (cls.unit_pattern if cls.unit_pattern and "{n}" not in cls.unit_pattern
                  else make_unit_id(cls, pos_id or room_id))
        )
        await self._request_control(cls, unit_id, value, room_id)

    async def _request_control(
        self,
        cls: DeviceClass,
        unit_id: str,
        value: Any,
        room_id: int,
    ) -> None:
        """제어 요청을 전송합니다 — Send a control request."""
        params: dict[str, str | int] = {
            "req_name": cls.req_name,
            "req_action": "control",
            "req_unit_num": unit_id or cls.unit_pattern or "null",
            "req_ctrl_action": str(value),
        }
        if cls.room_scoped:
            params["req_dev_num"] = room_id

        body = await self._request(
            cls.path,
            params,
            referer_path=REFERER_PAGES.get(cls.key, "/webapp/index.php"),
        )
        result, root = self._parse_xml_result(body)

        if result == RESULT_OK:
            LOGGER.info(
                "제어 성공 — %s %s=%s OK", cls.key, unit_id, value
            )
            # 제어 응답은 최신 상태를 그대로 포함하므로 직접 반영합니다.
            # The control response already echoes the post-state — apply it
            # directly instead of polling again (avoids a UI race where the
            # wallpad hasn't yet propagated the new state to a separate read).
            device_number = room_id if cls.room_scoped or cls.key == "temper" else 1
            for info in (root or ET.Element("imap")).findall(".//status_info"):
                self._dispatch_status(
                    cls,
                    device_number,
                    info.get("unit_num", ""),
                    info.get("unit_status", ""),
                    info,
                )
        else:
            LOGGER.warning(
                "제어 실패 — %s %s=%s result=%s", cls.key, unit_id, value, result,
            )


# 디렉터리 조회 헬퍼는 config_flow 에서 사용합니다.
# Directory-lookup helper used by config_flow (kept here to share the URL
# constant and to avoid pulling aiohttp into config_flow.py).


async def fetch_directory(session: aiohttp.ClientSession) -> list[dict[str, str]]:
    """단지 목록을 가져옵니다 — Fetch the i-parklife.com complex directory.

    Returns a list of normalised dicts. Empty list on any error so the config
    flow can fall back to manual IP entry.
    """
    from .iparkapp_const import DIRECTORY_URL

    out: list[dict[str, str]] = []
    try:
        async with session.get(
            DIRECTORY_URL, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            resp.raise_for_status()
            body = await resp.text()
    except aiohttp.ClientError as ex:
        LOGGER.warning("디렉터리 조회 실패 — Directory fetch failed: %s", ex)
        return out

    try:
        root = ET.fromstring(body)
    except ET.ParseError as ex:
        LOGGER.warning("디렉터리 XML 파싱 실패 — Directory XML parse failed: %s", ex)
        return out

    for item in root.findall("item"):
        out.append(
            {
                "sitecode": (item.findtext("SITECODE") or "").strip(),
                "sitename": (item.findtext("SITENAME") or "").strip(),
                "ip": (item.findtext("NETW_ADDR") or "").strip(),
                "weather": (item.findtext("SITEWEATHER") or "").strip(),
                "lat": (item.findtext("LAT") or "").strip(),
                "lng": (item.findtext("LNG") or "").strip(),
            }
        )
    return out
