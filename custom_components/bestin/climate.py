"""Climate platform for BESTIN"""

from __future__ import annotations

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN, ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_VERSION, LOGGER, NEW_CLIMATE
from .device import BestinDevice
from .hub import BestinHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Setup climate platform."""
    hub: BestinHub = BestinHub.get_hub(hass, entry)
    hub.entity_groups[CLIMATE_DOMAIN] = set()

    @callback
    def async_add_climate(devices=None):
        if devices is None:
            devices = hub.api.get_devices_from_domain(CLIMATE_DOMAIN)

        entities = [
            BestinClimate(device, hub) 
            for device in devices 
            if device.unique_id not in hub.entity_groups[CLIMATE_DOMAIN]
        ]

        if entities:
            async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, hub.async_signal_new_device(NEW_CLIMATE), async_add_climate
        )
    )
    async_add_climate()


class BestinClimate(BestinDevice, RestoreEntity, ClimateEntity):
    """Defined the Climate.

    ``RestoreEntity`` 는 슬로우 듀티 사이클 프리셋을 HA 재시작 후 되살리기
    위한 것입니다 (v1.4.11). 컨트롤러 상태는 메모리에만 있으므로, 복원이
    없으면 재시작할 때마다 모든 객실이 조용히 'none' 으로 떨어져 사용자가
    설정해 둔 난방 스케줄이 사라집니다.

    ``RestoreEntity`` is what brings the slow duty-cycle preset back after a
    restart (v1.4.11). The controller keeps its state in memory only, so
    without this every restart silently dropped every room to 'none' — the
    user's heating profile just disappeared, with nothing in the UI to say so.
    """

    TYPE = CLIMATE_DOMAIN

    # icons.json 의 climate.thermostat.state_attributes.preset_mode 에 매핑.
    # Maps preset_mode dropdown options to mdi icons (vacation→airplane,
    # frost→snowflake, etc.) via icons.json.
    _attr_translation_key = "thermostat"

    def __init__(self, device, hub: BestinHub):
        """Initialize the climate."""
        super().__init__(device, hub)
        # preset_modes 가 device state 에 있으면 PRESET_MODE 기능을 광고합니다.
        # If preset_modes is exposed in the device state, advertise the
        # PRESET_MODE feature so HA shows the standard preset dropdown.
        feats = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.TURN_ON |
            ClimateEntityFeature.TURN_OFF
        )
        if isinstance(self._device_info.state, dict) and self._device_info.state.get(
            "preset_modes"
        ):
            feats |= ClimateEntityFeature.PRESET_MODE
        self._supported_features = feats
        self._hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._version_exists = getattr(hub.api, CONF_VERSION, False)

    async def async_added_to_hass(self) -> None:
        """등록 시 마지막 상태를 복원합니다 — Restore last state on add."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            self.async_restore_last_state(last_state)

    @callback
    def async_restore_last_state(self, last_state: State) -> None:
        """듀티 사이클 프리셋 / setpoint 복원 — Re-arm the duty cycle.

        HA 는 마지막 상태를 최대 7일간 보관하므로, 재시작뿐 아니라 짧은 정전
        후에도 복원됩니다. 복원 대상은 두 가지 뿐입니다:

          - ``preset_mode`` — 사용자가 고른 프로파일. 이것이 핵심입니다.
          - ``temperature`` — 사용자가 프리셋 표준값 대신 직접 지정한 온도.
            듀티 사이클 활성 시 이 값이 곧 컨트롤러의 ``user_setpoint`` 입니다
            (iparkapp._dispatch_status 참고).

        나머지 (현재 온도, 사이클 위상, 듀티 %) 는 복원하지 않습니다 — 다음
        폴링과 첫 tick 이 30 s 안에 실제 값으로 다시 채웁니다. 재시작 중
        월패드가 어떤 상태였는지는 알 수 없으므로, 추측해서 복원하는 것보다
        관측된 온도로 처음부터 다시 계산하는 편이 정확합니다.

        HA keeps last states for up to 7 days, so this survives brief outages
        as well as ordinary restarts. Only two things are worth restoring:

          - ``preset_mode`` — the profile the user chose. This is the one that
            matters.
          - ``temperature`` — a setpoint the user picked instead of the
            preset's canonical value. While duty cycling, this *is* the
            controller's ``user_setpoint`` (see iparkapp._dispatch_status).

        Everything else (measured temperature, cycle phase, duty %) is left
        alone: the next poll and first tick refill it from reality within 30 s.
        We cannot know what the wallpad did while HA was down, so recomputing
        from an observed temperature beats restoring a guess.
        """
        # 듀티 사이클은 iparkapp 게이트웨이 전용입니다 — duty cycling exists
        # only on the iparkapp gateway; the other two have nothing to restore.
        restore = getattr(self.hub.api, "restore_duty_cycle_state", None)
        if not callable(restore):
            return

        preset = last_state.attributes.get(ATTR_PRESET_MODE)
        if not preset:
            return

        # 저장된 setpoint 는 사용자 데이터입니다 — 범위를 벗어나거나 숫자가
        # 아니면 무시하고 프리셋 표준값을 쓰게 둡니다.
        # The stored setpoint is user data: ignore anything non-numeric or out
        # of range and let the preset's canonical value stand.
        setpoint: float | None = None
        raw_setpoint = last_state.attributes.get(ATTR_TEMPERATURE)
        if isinstance(raw_setpoint, (int, float)) and not isinstance(
            raw_setpoint, bool
        ):
            if self.min_temp <= raw_setpoint <= self.max_temp:
                setpoint = float(raw_setpoint)
            else:
                LOGGER.warning(
                    "복원된 setpoint %.1f°C 가 범위(%d–%d)를 벗어나 무시합니다 — "
                    "restored setpoint for %s is out of range; using the "
                    "preset's canonical value instead",
                    raw_setpoint, self.min_temp, self.max_temp, self.entity_id,
                )

        if restore(self._device_info.room, preset, setpoint):
            LOGGER.info(
                "%s: 재시작 전 프리셋 '%s' 복원 — restored preset '%s' from "
                "before the restart",
                self.entity_id, preset, preset,
            )

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        return self._supported_features

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation ie. heat, cool mode.

        Need to be one of HVAC_MODE_*.
        """
        return self._device_info.state[ATTR_HVAC_MODE]

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available hvac operation modes."""
        return self._hvac_modes

    async def async_turn_on(self) -> None:
        """Turn the entity on."""

    async def async_turn_off(self) -> None:
        """Turn the entity off."""

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        if hvac_mode not in self.hvac_modes:
            raise ValueError(f"Unsupported HVAC mode {hvac_mode}")
        
        if self._version_exists:
            state = STATE_ON if hvac_mode == HVACMode.HEAT else STATE_OFF
            temp_payload = "{}/{}".format(state, self.target_temperature)
            await self.enqueue_command(room=temp_payload)
        else:
            await self.enqueue_command(mode=hvac_mode == HVACMode.HEAT)

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode (e.g., comfort, eco, sleep)."""
        if isinstance(self._device_info.state, dict):
            return self._device_info.state.get("preset_mode")
        return None

    @property
    def preset_modes(self) -> list[str] | None:
        """Return the list of available preset modes (or None if unsupported)."""
        if isinstance(self._device_info.state, dict):
            return self._device_info.state.get("preset_modes")
        return None

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode (forwarded to the gateway)."""
        await self.enqueue_command(preset_mode=preset_mode)

    @property
    def hvac_action(self):
        """Return the current action."""

    @property
    def extra_state_attributes(self) -> dict:
        """Surface duty-cycle controller telemetry alongside device attrs.

        iparkapp 게이트웨이에서 슬로우 듀티 사이클이 활성화된 객실은 컨트롤러의
        결정 상태 (``duty_cycle_pct`` / ``duty_cycle_phase`` /
        ``duty_cycle_period_s``) 를 climate 엔티티 속성으로 노출합니다.
        프리셋이 'none' 이거나 다른 게이트웨이에서는 키 자체가 없습니다.
        사용자가 별도 환수 온도 센서를 추가했을 때 동일 그래프 위에 컨트롤러
        의도값을 겹쳐 볼 수 있도록 v1.4.9 에서 추가됩니다.

        On the iparkapp gateway, surface the duty-cycle controller's decision
        state as climate attributes (``duty_cycle_pct`` /
        ``duty_cycle_phase`` / ``duty_cycle_period_s``). On other gateways
        and on the 'none' preset, the keys are simply absent. Added in v1.4.9
        so users adding an optional return-water temperature probe can graph
        controller intent and actual heat absorption on the same chart.
        """
        attrs = super().extra_state_attributes
        if isinstance(self._device_info.state, dict):
            for key in ("duty_cycle_pct", "duty_cycle_phase", "duty_cycle_period_s"):
                val = self._device_info.state.get(key)
                if val is not None:
                    attrs[key] = val
        return attrs

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._device_info.state[ATTR_CURRENT_TEMPERATURE]

    @property
    def target_temperature(self) -> float:
        """Return the target temperature."""
        return self._device_info.state[SERVICE_SET_TEMPERATURE]

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ValueError(f"Expected attribute {ATTR_TEMPERATURE}")
        temperature = float(kwargs[ATTR_TEMPERATURE])
        
        if self._version_exists:
            temp_payload = "{}/{}/{}".format(STATE_ON, temperature, self.current_temperature)
            await self.enqueue_command(room=temp_payload)
        else:
            await self.enqueue_command(set_temperature=temperature)

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def max_temp(self) -> int:
        """Max tempreature."""
        return 40

    @property
    def min_temp(self) -> int:
        """Min tempreature."""
        return 5

    @property
    def target_temperature_step(self) -> float:
        """Step temperature.

        iparkapp 게이트웨이의 클라우드 서버는 정수 setpoint 만 받습니다 (live
        probe 로 확인됨: 22.5 를 보내도 22 로 echo). 사용자에게 사용할 수 없는
        해상도를 노출하지 않도록 1.0 으로 고정합니다. RS-485/HDC 경로는 영향
        없습니다.
        The iparkapp cloud server stores integer setpoints only (verified by
        live probe — sending 22.5 echoes back as 22). Advertising 1.0 here
        keeps the HA UI honest. RS-485 / HDC paths are unaffected.
        """
        return 1.0 if self._version_exists else 0.5
