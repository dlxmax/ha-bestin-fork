"""Config flow to configure BESTIN."""

from __future__ import annotations
from typing import Any

import asyncio
import voluptuous as vol

from homeassistant.core import callback
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
    SOURCE_IMPORT,
)
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_UUID,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    __version__ as HA_VERSION,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.loader import async_get_integration

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    selector,
)
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .hub import BestinHub
from .const import (
    DOMAIN,
    LOGGER,
    CONF_VERSION,
    CONF_VERSION_1,
    CONF_VERSION_2,
    CONF_SESSION,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_MAX_SEND_RETRY,
    DEFAULT_PACKET_VIEWER,
)
from .iparkapp import fetch_directory
from .report import (
    build_issue_url,
    collect_secrets,
    error_text,
    flow_error_blocks,
    issue_title,
    scrub_text,
)
from .iparkapp_const import (
    CONF_IPARKAPP_PASSWORD,
    CONF_IPARKAPP_SITE,
    CONF_IPARKAPP_USERNAME,
    DEFAULT_POLL_INTERVAL,
    LOGIN_DATA_PATH,
    LOGIN_LANDING_PATH,
    ROOM_PROBE_RANGE,
    USER_AGENT,
    room_temp_sensor_key,
)


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BESTIN."""

    VERSION = 1
    data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(entry)
    
    @staticmethod
    def int_between(min_int, max_int):
        """Return an integer between 'min_int' and 'max_int'."""
        return vol.All(vol.Coerce(int), vol.Range(min=min_int, max=max_int))

    async def _error_placeholders(
        self, step: str, exc: BaseException, user_input: dict[str, Any] | None
    ) -> dict[str, str]:
        """예상하지 못한 오류를 화면에 보이고 신고 링크를 만듭니다.

        아직 항목이 없어 진단을 내려받을 수 없는 단계입니다. 그래서 실제 오류와
        BESTIN 코드의 traceback 을 담은 GitHub 링크를 양식에 보여줍니다.

        Show an unexpected error on the form with a report link. No entry exists
        yet, so diagnostics can't be downloaded; the link carries the real error
        and the BESTIN frames of the traceback instead.
        """
        LOGGER.exception("설정 오류 / Setup step '%s' failed", step)
        secrets = collect_secrets({"input": user_input or {}, "site": self.data})
        try:
            version = str((await async_get_integration(self.hass, DOMAIN)).version)
        except Exception:  # noqa: BLE001
            version = None
        title = issue_title(f"setup:{step}", version, error_text(exc))
        url, _body = build_issue_url(
            scrub_text(title, secrets),
            "",
            flow_error_blocks(step, exc, version, HA_VERSION, secrets),
            attach_note=False,
        )
        return {
            "err": scrub_text(error_text(exc), secrets)[:300],
            "report": (
                "\n\n**[GitHub 에 문제 신고 / Report this on GitHub]("
                + url
                + ")** (내용은 GitHub 에서 확인 후 제출 / review it on GitHub before submitting)"
            ),
        }

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["local", "center", "iparkapp"],
        )

    async def async_step_local(
        self, 
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle local communication setup."""
        errors = {}
        placeholders = {"err": "", "report": ""}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            hub = None
            connected = False

            try:
                hub = BestinHub(self.hass, entry=None)
                connected = await asyncio.wait_for(hub.connect(host, port), timeout=5)
            except asyncio.TimeoutError as ex:
                LOGGER.error(f"Connection to {host}:{port} failed due to timeout: {ex}")
                errors["base"] = "connect_failed"
            except Exception as ex:  # noqa: BLE001 / show the real error (issue #4)
                errors["base"] = "unknown_detail"
                placeholders = await self._error_placeholders("local", ex, user_input)
            finally:
                # 연결 확인용 소켓은 닫습니다. 항목이 설정되면 새로 엽니다.
                # Close the probe connection; setup opens its own.
                if hub is not None and hub.connection is not None:
                    try:
                        await hub.connection.close()
                    except Exception:  # noqa: BLE001
                        pass

            if not errors and not connected:
                errors["base"] = "connect_failed"
            if not errors:
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_HOST], data=user_input)

        return self.async_show_form(
            step_id="local",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
            }),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _v1_server_login(self, user_input, session) -> Any:
        """Login to the I'Park Smart Home server (v1) and retrieve session cookies."""
        url = f"http://{user_input[CONF_IP_ADDRESS]}/webapp/data/getLoginWebApp.php"
        params = {
            "login_ide": user_input[CONF_USERNAME],
            "login_pwd": user_input[CONF_PASSWORD],
        }

        try:
            async with session.get(url=url, params=params, timeout=5) as response:
                resp = await response.json(content_type="text/html")

                if response.status == 200 and "_fair" not in resp["ret"]:
                    cookies = response.cookies
                    new_cookie = {
                        "PHPSESSID": cookies.get("PHPSESSID").value if cookies.get("PHPSESSID") else None,
                        "user_id": cookies.get("user_id").value if cookies.get("user_id") else None,
                        "user_name": cookies.get("user_name").value if cookies.get("user_name") else None,
                    }
                    LOGGER.info(f"V1 login successful. Response: {resp}, Cookies: {new_cookie}")
                    return new_cookie, None
                elif "_fair" in resp["ret"]:
                    LOGGER.error(f"V1 login failed (200): Invalid credentials. {resp['msg']}")
                    return None, ("login_failed", resp["msg"])
                else:
                    LOGGER.error(f"V1 login failed. Status: {response.status}")
                    return None, ("network_error", None)

        except Exception as ex:
            LOGGER.error(f"V1 Login exception: {type(ex).__name__}. Details: {ex}")
            return None, ("unknown_detail", ex)

    async def _v2_server_login(self, user_input, session) -> Any:
        """Login to the I'Park Smart Home server (v2) and retrieve session cookies."""
        url = "https://center.hdc-smart.com/v3/auth/login"
        headers = {
            "Content-Type": "application/json",
            "Authorization": user_input[CONF_UUID],
            "User-Agent": "mozilla/5.0 (windows nt 10.0; win64; x64) applewebkit/537.36 (khtml, like gecko) chrome/78.0.3904.70 safari/537.36"
        }

        try:
            async with session.post(url=url, headers=headers, timeout=5) as response:
                resp = await response.json()
        
                if response.status == 200:
                    LOGGER.info(f"V2 login successful: {resp}")
                    return resp, None
                elif response.status == 500:
                    LOGGER.error(f"V2 login failed (500): {resp["err"]}")
                    return None, ("login_failed", resp["err"])
                else:
                    LOGGER.error(f"V2 login failed. Status: {response.status}")
                    return None, ("network_error", None)
        
        except Exception as ex:
            LOGGER.error(f"V2 Login exception: {type(ex).__name__}. Details: {ex}")
            return None, ("unknown_detail", ex)

    async def _login_error_placeholders(
        self, step: str, detail: Any, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """로그인 오류 내용을 양식용 값으로 / Login error detail for the form.

        v1.4.22 까지 v2 는 ``detail["msg"]`` 를 바로 읽어서, 네트워크 오류
        (detail 이 None) 때 TypeError 로 '알 수 없는 오류' 가 났습니다.
        Through v1.4.22 v2 read ``detail["msg"]`` directly, so a network error
        (detail None) crashed with TypeError and showed "unknown error".
        """
        if isinstance(detail, BaseException):
            return await self._error_placeholders(step, detail, user_input)
        if isinstance(detail, dict):
            detail = detail.get("msg", detail)
        return {"err": "" if detail is None else str(detail), "report": ""}

    async def async_step_center(
        self, 
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user selection for center version."""
        errors = {}

        if user_input is not None:
            if user_input[CONF_VERSION] == CONF_VERSION_1:
                return await self.async_step_center_v1()
            else:
                return await self.async_step_center_v2()

        return self.async_show_form(
            step_id="center",
            data_schema=vol.Schema({
                "version": selector({
                    "select": {
                        "options": [CONF_VERSION_1, CONF_VERSION_2],
                        "mode": "dropdown",
                    }
                })
            }),
            errors=errors,
        )

    async def async_step_center_v1(
        self, 
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the center version 1."""
        errors = {}
        description_placeholders = {"err": "", "report": ""}

        if user_input is not None:
            session = async_create_clientsession(self.hass)

            response, error_message = await self._v1_server_login(user_input, session)

            if error_message:
                errors["base"] = error_message[0]
                description_placeholders = await self._login_error_placeholders(
                    "center_v1", error_message[1], user_input
                )
            else:
                user_input[CONF_SESSION] = response
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_USERNAME], data=user_input)

        data_schema = vol.Schema({
            vol.Required(CONF_IP_ADDRESS): cv.string,
            vol.Required(CONF_USERNAME): cv.string,
            vol.Required(CONF_PASSWORD): cv.string,
        })

        return self.async_show_form(
            step_id="center_v1",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders
        )

    async def async_step_center_v2(
        self,
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the center version 2."""
        errors = {}
        description_placeholders = {"err": "", "report": ""}

        if user_input is not None:
            session = async_create_clientsession(self.hass)

            response, error_message = await self._v2_server_login(user_input, session)

            if error_message:
                errors["base"] = error_message[0]
                description_placeholders = await self._login_error_placeholders(
                    "center_v2", error_message[1], user_input
                )
            else:
                user_input[CONF_SESSION] = response
                await self.async_set_unique_id(user_input[CONF_UUID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_UUID], data=user_input)

        data_schema = vol.Schema({
            vol.Required("elevator_number", default=1): ConfigFlow.int_between(1, 4),
            vol.Optional(CONF_IP_ADDRESS): cv.string,
            vol.Required(CONF_UUID): cv.string,
        })

        return self.async_show_form(
            step_id="center_v2",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders
        )


    # ------------------------------------------------------------------
    # iPark 스마트홈 앱 — new gateway type config flow
    # iPark Smarthome App config flow
    # ------------------------------------------------------------------

    async def async_step_iparkapp(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """단지 선택 단계 — Step 1: pick the apartment complex."""
        errors: dict[str, str] = {}
        session = async_create_clientsession(self.hass)

        # 디렉터리를 로딩하고 셀렉터에 표시합니다 — Try the directory first.
        directory = await fetch_directory(session)
        site_choices = {
            f"{item['sitecode']}|{item['ip']}": f"{item['sitename']} ({item['ip']})"
            for item in directory
            if item.get("sitecode") and item.get("ip") and item.get("sitename")
        }

        if user_input is not None:
            picked = user_input.get("site")
            if picked == "__manual__" or not directory:
                # 매뉴얼 입력 단계로 전환 — Switch to manual entry.
                return await self.async_step_iparkapp_manual()

            sitecode, ip = picked.split("|", 1)
            match = next(
                (it for it in directory if it.get("sitecode") == sitecode), None
            )
            if match is None:
                errors["base"] = "directory_lookup_failed"
            else:
                self.data = {CONF_IPARKAPP_SITE: match}
                return await self.async_step_iparkapp_login()

        if not site_choices:
            # 디렉터리 응답 실패 시 매뉴얼로 폴백 — Fall back to manual on directory error.
            return await self.async_step_iparkapp_manual()

        # 매뉴얼 입력 옵션 추가 — Append a manual-entry option to the dropdown.
        choices = dict(site_choices)
        choices["__manual__"] = "직접 입력 / Enter manually"

        data_schema = vol.Schema(
            {
                vol.Required("site"): selector(
                    {
                        "select": {
                            "options": [
                                {"value": k, "label": v} for k, v in choices.items()
                            ],
                            "mode": "dropdown",
                        }
                    }
                ),
            }
        )
        return self.async_show_form(
            step_id="iparkapp",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_iparkapp_manual(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """단지 정보 직접 입력 — Step 1b: manually enter the site fields."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.data = {
                CONF_IPARKAPP_SITE: {
                    "sitecode": user_input.get("sitecode", "").strip(),
                    "sitename": user_input.get("sitename", "").strip()
                                 or user_input["ip"].strip(),
                    "ip": user_input["ip"].strip(),
                    "weather": user_input.get("weather", "").strip(),
                    "lat": user_input.get("lat", "").strip(),
                    "lng": user_input.get("lng", "").strip(),
                }
            }
            return await self.async_step_iparkapp_login()

        data_schema = vol.Schema(
            {
                vol.Required("ip"): cv.string,
                vol.Optional("sitename", default=""): cv.string,
                vol.Optional("sitecode", default=""): cv.string,
                vol.Optional("weather", default=""): cv.string,
                vol.Optional("lat", default=""): cv.string,
                vol.Optional("lng", default=""): cv.string,
            }
        )
        return self.async_show_form(
            step_id="iparkapp_manual",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_iparkapp_login(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """로그인 단계 — Step 2: username + password (no token copy-paste needed)."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {"err": "", "report": ""}

        if user_input is not None:
            session = async_create_clientsession(self.hass)
            site = self.data[CONF_IPARKAPP_SITE]
            ok, err = await self._iparkapp_verify_login(
                session,
                site,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if not ok and isinstance(err, BaseException):
                errors["base"] = "unknown_detail"
                description_placeholders = await self._error_placeholders(
                    "iparkapp_login", err, user_input
                )
            elif not ok:
                errors["base"] = err or "login_failed"
                description_placeholders = {"err": "", "report": ""}
            else:
                entry_data = {
                    CONF_IPARKAPP_SITE: site,
                    CONF_IPARKAPP_USERNAME: user_input[CONF_USERNAME],
                    CONF_IPARKAPP_PASSWORD: user_input[CONF_PASSWORD],
                }
                # 단지 IP + 사용자명을 unique_id 로 사용 (한 사용자가 여러 단지 가능)
                # Use site IP + username as the unique_id (a user can pair to >1 site).
                unique_id = f"iparkapp:{site['ip']}:{user_input[CONF_USERNAME]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                title = (
                    f"{site.get('sitename') or site['ip']} "
                    f"— {user_input[CONF_USERNAME]}"
                )
                return self.async_create_entry(title=title, data=entry_data)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )
        return self.async_show_form(
            step_id="iparkapp_login",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    @staticmethod
    async def _iparkapp_verify_login(
        session,
        site: dict[str, str],
        username: str,
        password: str,
    ) -> tuple[bool, str | BaseException | None]:
        """로그인 확인 — Run the 2-step login to verify credentials.

        Returns ``(True, None)`` on success or ``(False, error_key)`` where
        ``error_key`` is one of the keys translated in the JSON files, or the
        exception itself when something unexpected went wrong.
        """
        ip = site["ip"]
        landing_url = f"http://{ip}{LOGIN_LANDING_PATH}"
        landing_params = {
            "device": "WA",
            "login_ide": username,
            "login_pwd": password,
            "SITEWeather": site.get("weather", ""),
            "SITELat": site.get("lat", ""),
            "SITELng": site.get("lng", ""),
        }
        try:
            async with session.get(
                landing_url,
                params=landing_params,
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            ) as resp:
                if resp.status >= 400:
                    return False, "network_error"

            data_url = f"http://{ip}{LOGIN_DATA_PATH}"
            data_body = {
                "device": "WA",
                "login_ide": username,
                "login_pwd": password,
                "siteweather": site.get("weather", ""),
                "sitelat": site.get("lat", ""),
                "sitelng": site.get("lng", ""),
            }
            async with session.post(
                data_url,
                data=data_body,
                headers={
                    "User-Agent": USER_AGENT,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
                timeout=10,
            ) as resp:
                payload = await resp.json(content_type=None)
                if payload.get("ret") == "success":
                    return True, None
                return False, "login_failed"
        except asyncio.TimeoutError:
            return False, "connect_failed"
        except Exception as ex:  # pragma: no cover — defensive
            LOGGER.warning("iparkapp login verify exception: %s", ex)
            return False, ex


class OptionsFlowHandler(OptionsFlow):
    """Handle an option flow for BESTIN."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.entry = entry
    
    def get_data_schema(self) -> vol.Schema:
        """Get the appropriate schema based on the entry data."""
        # iPark 스마트홈 앱 — new gateway type takes its own option panel.
        if CONF_IPARKAPP_SITE in self.entry.data:
            fields: dict[Any, Any] = {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_POLL_INTERVAL
                    ),
                ): cv.positive_int,
            }
            # v1.4.16: 객실별 실내 온도 센서 (선택). suggested_value 를 써야
            # 사용자가 칸을 비웠을 때 매핑이 실제로 지워집니다.
            # v1.4.16: optional per-room temperature sensor. suggested_value
            # (not default) so clearing the field really removes the mapping.
            for room in self._iparkapp_rooms():
                key = room_temp_sensor_key(room)
                fields[
                    vol.Optional(
                        key,
                        description={"suggested_value": self.entry.options.get(key)},
                    )
                ] = selector(
                    {
                        "entity": {
                            "filter": {
                                "domain": "sensor",
                                "device_class": "temperature",
                            }
                        }
                    }
                )
            return vol.Schema(fields)
        if CONF_SESSION not in self.entry.data:
            return vol.Schema({
                vol.Required(
                    "max_send_retry",
                    default=self.entry.options.get("max_send_retry", DEFAULT_MAX_SEND_RETRY)
                ): ConfigFlow.int_between(1, 30),
                vol.Required(
                    "packet_viewer",
                    default=self.entry.options.get("packet_viewer", DEFAULT_PACKET_VIEWER)
                ): cv.boolean,
            })
        return vol.Schema({
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ): cv.positive_int,
        })

    def _iparkapp_thermostats(self) -> dict[int, str]:
        """방 번호별 온도조절기 이름: Room number to thermostat name.

        통합이 로드되어 있으면 실제 온도조절기만, 아니면 탐색 범위 전체를
        보여줍니다. Lists the real thermostats when the integration is
        loaded, otherwise the whole probe range.
        """
        hub = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        devices = getattr(getattr(hub, "api", None), "devices", None) or {}
        registry = er.async_get(self.hass)
        rooms: dict[int, str] = {}
        for room in ROOM_PROBE_RANGE:
            device = devices.get(f"bestin_temper_{room}")
            if device is None:
                continue
            entity_id = registry.async_get_entity_id(
                "climate", DOMAIN, device.unique_id
            )
            state = self.hass.states.get(entity_id) if entity_id else None
            rooms[room] = state.name if state is not None else entity_id or str(room)
        if not rooms:
            rooms = {room: str(room) for room in ROOM_PROBE_RANGE}
        return rooms

    def _iparkapp_rooms(self) -> list[int]:
        return list(self._iparkapp_thermostats())

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """옵션 메뉴 / Options menu: settings, or report a problem (v1.4.23)."""
        if self.entry.source == SOURCE_IMPORT:
            return self.async_show_form(step_id="init", data_schema=None)
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "report"],
        )

    async def async_step_settings(
        self,
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options flow."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        rooms = ""
        if CONF_IPARKAPP_SITE in self.entry.data:
            rooms = "\n".join(
                f"- {room}: {name}"
                for room, name in self._iparkapp_thermostats().items()
            )
        return self.async_show_form(
            step_id="settings",
            data_schema=self.get_data_schema(),
            errors=errors,
            description_placeholders={"rooms": rooms},
        )

    async def async_step_report(
        self,
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """문제 신고 / Report a problem.

        사용자가 적은 내용과 가린 요약으로 GitHub 새 이슈 링크를 만듭니다.
        통합은 아무것도 보내지 않고, 사용자가 GitHub 에서 확인 후 제출합니다.
        Builds a GitHub new-issue link from what the user typed plus the
        redacted summary. Nothing is sent: the user reviews and submits it.
        """
        if user_input is not None:
            # diagnostics 는 HA 의 diagnostics 구성요소를 불러오므로 필요할 때만
            # 가져옵니다. Imported on use: it pulls in HA's diagnostics component.
            from .diagnostics import async_build_report

            url, body = await async_build_report(
                self.hass, self.entry, user_input.get("description", "")
            )
            # 옵션을 건드리지 않고 끝내려고 abort 를 씁니다. 빈 data 로
            # create_entry 를 하면 옵션이 지워집니다.
            # Abort ends the flow without touching options; create_entry with
            # empty data would wipe them.
            return self.async_abort(
                reason="report_ready",
                description_placeholders={"url": url, "summary": body},
            )
        return self.async_show_form(
            step_id="report",
            data_schema=vol.Schema(
                {
                    vol.Optional("description", default=""): TextSelector(
                        TextSelectorConfig(multiline=True)
                    ),
                }
            ),
        )
