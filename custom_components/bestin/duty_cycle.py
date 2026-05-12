"""온돌 슬로우 듀티 사이클 제어기 — Slow duty-cycle controller for Korean ondol thermostats.

월패드의 이진 on/off 와 setpoint 만으로는 바닥난방의 큰 열관성에 비해 너무 거친
제어가 됩니다. 본 모듈은 minutes 단위 사이클로 부드러운 비례 제어를 적용합니다
(빠른 PWM 이 아니라 분 단위의 슬로우 시간 비례 제어 — duty cycle 변조).
파라미터는 ``temp/research/ondol_duty_cycle_research.md`` 의 연구 결과
(IEA / ASHRAE / EN / VDI / OJ Electronics 등) 에서 가져왔습니다.

The wallpad's binary on/off + setpoint is too coarse for the high thermal mass
of a Korean radiant floor. This module layers a *slow duty-cycle* (time-
proportional) controller on top — cycle periods are minutes, not microseconds,
so this is duty-cycle / time-proportional control, not high-frequency PWM.
All parameters are sourced from the research archived at
``temp/research/ondol_duty_cycle_research.md`` (IEA, ASHRAE, EN 12531,
VDI 6030, OJ Electronics, Honeywell, Uponor — see the doc for citations).

설계 원칙 / Design principles:
  - 비례 제어 (P) + 데드밴드 — proportional control with deadband.
  - 사이클당 최소 on / off 시간 — minimum on/off times per cycle.
  - 셋포인트 근접 시 듀티 감소 — anti-overshoot duty reduction near setpoint.
  - 객실별 프리셋 — per-room preset (each room may run a different profile).
  - 게이트웨이 독립 — gateway-agnostic: callers inject a send-command callback,
    so iparkapp / center / controller can all use the same controller.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from .const import LOGGER


# ---------------------------------------------------------------------------
# 표준 HA preset_mode 이름 — Standard HA preset_mode names.
# ---------------------------------------------------------------------------
# Aligned with the canonical names HA's climate component recognises across
# vendors (Nest, EvoHome, Ecobee, etc.) so users get a familiar dropdown.

PRESET_NONE = "none"          # passthrough; no duty cycling, wallpad's own logic only
PRESET_COMFORT = "comfort"    # active occupancy
PRESET_ECO = "eco"            # cost-conscious
PRESET_SLEEP = "sleep"        # overnight setback
PRESET_AWAY = "away"          # short trip / work day
PRESET_VACATION = "vacation"  # multi-day absence
PRESET_FROST = "frost"        # long-term unoccupied / pipe protection
PRESET_BOOST = "boost"        # post-vacation recovery (reserve for occasional)

PRESET_MODES_DEFAULT: tuple[str, ...] = (
    PRESET_NONE,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_SLEEP,
    PRESET_AWAY,
    PRESET_VACATION,
    PRESET_FROST,
    PRESET_BOOST,
)


@dataclass(frozen=True)
class PresetProfile:
    """프리셋별 듀티 사이클 + 셋포인트 — Profile for one preset.

    ``cycle_period_s == 0`` means "no duty cycling" — the callback is not
    invoked on a cycle; the controller just publishes the canonical setpoint
    to the gateway and lets the wallpad's onboard logic handle on/off.
    """

    name: str
    canonical_setpoint_c: float    # the setpoint this preset maps to
    cycle_period_s: int             # 0 = no duty cycling (passthrough)
    proportional_band_c: float
    min_on_s: int
    min_off_s: int
    deadband_pct: float
    overshoot_guard_c: float = 0.5
    overshoot_factor: float = 0.8


# 프리셋 → 프로파일. 연구 §10.7 + §12 의 권장값에서 가져옴.
# Profiles drawn from research §10.7 + §12 recommended defaults.
PRESET_PROFILES: dict[str, PresetProfile] = {
    PRESET_NONE: PresetProfile(
        name=PRESET_NONE, canonical_setpoint_c=22.0,
        cycle_period_s=0,  # duty cycling disabled
        proportional_band_c=0.0, min_on_s=0, min_off_s=0, deadband_pct=0.0,
    ),
    PRESET_COMFORT: PresetProfile(
        name=PRESET_COMFORT, canonical_setpoint_c=22.0,
        cycle_period_s=15 * 60, proportional_band_c=2.0,
        min_on_s=120, min_off_s=60, deadband_pct=5.0,
    ),
    PRESET_ECO: PresetProfile(
        name=PRESET_ECO, canonical_setpoint_c=20.0,
        cycle_period_s=20 * 60, proportional_band_c=2.5,
        min_on_s=120, min_off_s=90, deadband_pct=8.0,
    ),
    PRESET_SLEEP: PresetProfile(
        name=PRESET_SLEEP, canonical_setpoint_c=17.0,
        cycle_period_s=25 * 60, proportional_band_c=3.0,
        min_on_s=120, min_off_s=120, deadband_pct=10.0,
    ),
    PRESET_AWAY: PresetProfile(
        name=PRESET_AWAY, canonical_setpoint_c=16.0,
        cycle_period_s=25 * 60, proportional_band_c=3.0,
        min_on_s=120, min_off_s=120, deadband_pct=10.0,
    ),
    PRESET_VACATION: PresetProfile(
        name=PRESET_VACATION, canonical_setpoint_c=13.0,
        cycle_period_s=30 * 60, proportional_band_c=4.0,
        min_on_s=120, min_off_s=180, deadband_pct=15.0,
    ),
    PRESET_FROST: PresetProfile(
        name=PRESET_FROST, canonical_setpoint_c=9.0,
        cycle_period_s=30 * 60, proportional_band_c=5.0,
        min_on_s=180, min_off_s=180, deadband_pct=20.0,
    ),
    PRESET_BOOST: PresetProfile(
        name=PRESET_BOOST, canonical_setpoint_c=23.0,
        cycle_period_s=10 * 60, proportional_band_c=1.5,
        min_on_s=120, min_off_s=30, deadband_pct=3.0,
    ),
}


TICK_INTERVAL_S = 30


# ---------------------------------------------------------------------------
# 객실별 상태 — Per-room state
# ---------------------------------------------------------------------------

@dataclass
class RoomDutyCycleState:
    """객실 듀티 사이클 상태 — Per-room state (keyed by room number)."""

    room: int
    preset: str = PRESET_NONE
    user_setpoint: float = 22.0
    current_temp: float = 0.0
    target_duty_pct: float = 0.0
    last_sent_phase: bool | None = None  # True = on, False = off, None = never
    cycle_started_at: datetime = field(default_factory=datetime.now)
    phase_started_at: datetime = field(default_factory=datetime.now)


# Type alias for the gateway-supplied send callback.
# 콜백은 (room, ctrl_action_string) 을 받아 월패드에 비동기로 송신합니다.
# Signature: (room: int, ctrl_action: str) -> awaitable; ctrl_action is e.g.
# "on/27" or "off/22" — the same string the wallpad's req_ctrl_action expects.
SendCommand = Callable[[int, str], Awaitable[None]]


class DutyCycleController:
    """객실별 비례 듀티 사이클 컨트롤러 — Per-room proportional duty-cycle controller.

    한 인스턴스가 모든 객실을 관리하며 객실마다 별개의 프리셋을 가질 수 있습니다.
    게이트웨이별 송신 로직은 ``send_command`` 콜백에 주입됩니다.
    빠른 PWM 이 아니라 분 단위 시간 비례 제어 (slow duty cycle) 입니다.

    A single instance manages all rooms; each room can be on its own preset.
    Gateway-specific send logic is injected via the ``send_command`` callback.
    This is *slow* (minutes-scale) time-proportional control, not high-
    frequency PWM — the term "duty cycle" refers to the on-time ratio per
    cycle.
    """

    def __init__(
        self,
        send_command: SendCommand,
        on_state_change: Callable[[int, RoomDutyCycleState], None] | None = None,
    ) -> None:
        self._send = send_command
        self._on_state_change = on_state_change
        self.rooms: dict[int, RoomDutyCycleState] = {}
        self._stop_event: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task | None = None

    # ----- lifecycle --------------------------------------------------------

    def start(self, hass: Any) -> None:
        """틱 루프 시작 — Start the tick loop."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = hass.loop.create_task(self._run())
        LOGGER.info(
            "듀티 사이클 컨트롤러 시작 — DutyCycleController started "
            "(per-room presets)"
        )

    async def stop(self) -> None:
        """틱 루프 정지 — Stop the tick loop."""
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._task = None

    # ----- public API -------------------------------------------------------

    def set_preset(self, room: int, preset: str) -> PresetProfile:
        """객실 프리셋 변경 — Change a room's preset; returns the active profile.

        The canonical setpoint of the new preset becomes the user_setpoint
        unless the user explicitly sets a different value with ``set_setpoint``.
        """
        if preset not in PRESET_PROFILES:
            LOGGER.warning("Unknown preset %r; falling back to 'none'", preset)
            preset = PRESET_NONE
        st = self._get_or_create(room)
        st.preset = preset
        st.user_setpoint = PRESET_PROFILES[preset].canonical_setpoint_c
        # 프리셋 전환 시 즉시 한 번 적용되도록 phase 를 reset 합니다.
        # Reset the phase so the new preset takes effect on the next tick
        # rather than waiting out the current cycle.
        st.cycle_started_at = datetime.now()
        st.last_sent_phase = None
        if self._on_state_change is not None:
            self._on_state_change(room, st)
        LOGGER.info(
            "듀티 사이클 객실 %s → preset %s (setpoint=%.1f°C, cycle=%ds)",
            room, preset, st.user_setpoint,
            PRESET_PROFILES[preset].cycle_period_s,
        )
        return PRESET_PROFILES[preset]

    def set_setpoint(self, room: int, setpoint: float) -> None:
        """사용자 setpoint 변경 — User changed the setpoint via HA."""
        st = self._get_or_create(room)
        st.user_setpoint = setpoint
        if self._on_state_change is not None:
            self._on_state_change(room, st)
        LOGGER.info("듀티 사이클 객실 %s setpoint → %.1f°C", room, setpoint)

    def upsert_current_temp(self, room: int, current_temp: float | None) -> None:
        """폴링 시 호출 — Called from polling to update the measured temp."""
        if current_temp is None:
            return
        st = self._get_or_create(room)
        st.current_temp = current_temp

    def get_room(self, room: int) -> RoomDutyCycleState | None:
        return self.rooms.get(room)

    def is_active_for(self, room: int) -> bool:
        """이 객실이 듀티 사이클로 제어 중인가? — Does the duty-cycle controller currently drive this room?"""
        st = self.rooms.get(room)
        if st is None:
            return False
        prof = PRESET_PROFILES[st.preset]
        return prof.cycle_period_s > 0

    # ----- internal --------------------------------------------------------

    def _get_or_create(self, room: int) -> RoomDutyCycleState:
        st = self.rooms.get(room)
        if st is None:
            st = RoomDutyCycleState(room=room)
            self.rooms[room] = st
        return st

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception as ex:  # noqa: BLE001
                LOGGER.exception("duty-cycle tick error: %s", ex)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=TICK_INTERVAL_S
                )
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        now = datetime.now()
        for state in list(self.rooms.values()):
            profile = PRESET_PROFILES[state.preset]
            if profile.cycle_period_s == 0:
                continue  # passthrough preset (e.g. none); skip
            duty = self._compute_duty(state, profile)
            should_be_on = self._decide_phase(state, profile, duty, now)
            if should_be_on == state.last_sent_phase:
                continue
            elapsed = (now - state.phase_started_at).total_seconds()
            if state.last_sent_phase is True and elapsed < profile.min_on_s:
                continue
            if state.last_sent_phase is False and elapsed < profile.min_off_s:
                continue
            await self._apply(state, should_be_on, now)
            state.target_duty_pct = duty

    @staticmethod
    def _compute_duty(state: RoomDutyCycleState, profile: PresetProfile) -> float:
        error = state.user_setpoint - state.current_temp
        duty = max(0.0, min(100.0, (error / profile.proportional_band_c) * 100.0))
        if 0 < error < profile.overshoot_guard_c and duty > 50.0:
            duty *= profile.overshoot_factor
        return duty

    @staticmethod
    def _decide_phase(
        state: RoomDutyCycleState,
        profile: PresetProfile,
        duty: float,
        now: datetime,
    ) -> bool:
        cycle_s = profile.cycle_period_s
        elapsed_in_cycle = (now - state.cycle_started_at).total_seconds()
        if elapsed_in_cycle >= cycle_s:
            state.cycle_started_at = now
            elapsed_in_cycle = 0.0
        on_duration_s = cycle_s * (duty / 100.0)
        return elapsed_in_cycle < on_duration_s

    async def _apply(
        self, state: RoomDutyCycleState, should_be_on: bool, now: datetime
    ) -> None:
        """월패드에 명령 전송 — Issue the on/off pulse via the injected callback.

        On-pulse: setpoint elevated to current+5°C so the wallpad's onboard
        threshold actually calls for heat. Off-pulse: send the user's true
        setpoint so any external observer sees a sensible value at rest.
        """
        forced = state.current_temp + 5 if should_be_on else state.user_setpoint
        verb = "on" if should_be_on else "off"
        ctrl = f"{verb}/{forced:g}"
        LOGGER.debug(
            "듀티 사이클 객실 %s → %s (preset=%s, duty=%.1f%%, current=%.1f, "
            "setpoint=%.1f, sent=%s)",
            state.room, "ON" if should_be_on else "OFF", state.preset,
            state.target_duty_pct, state.current_temp, state.user_setpoint, ctrl,
        )
        try:
            await self._send(state.room, ctrl)
        except Exception as ex:  # noqa: BLE001
            LOGGER.warning(
                "duty-cycle apply failed for room %s: %s", state.room, ex
            )
            return
        state.last_sent_phase = should_be_on
        state.phase_started_at = now
        if self._on_state_change is not None:
            self._on_state_change(state.room, state)
