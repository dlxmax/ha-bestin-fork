"""온돌 슬로우 PWM 제어기 — Slow PWM controller for Korean ondol thermostats.

월패드의 이진 on/off 와 setpoint 만으로는 바닥난방의 열관성에 비해 너무 거친
제어가 됩니다. 본 모듈은 minutes 단위 사이클로 부드러운 비례 제어를 적용합니다.
파라미터는 ``temp/research/ondol_pwm_research.md`` 의 연구 결과 (IEA / ASHRAE /
EN / VDI / OJ Electronics 등) 에서 가져왔습니다.

The wallpad's binary on/off + setpoint is too coarse for the high thermal mass
of a Korean radiant floor. This module layers a slow proportional PWM on top —
all parameters are sourced from the research archived at
``temp/research/ondol_pwm_research.md`` (IEA, ASHRAE, EN 12531, VDI 6030,
OJ Electronics, Honeywell, Uponor — see the doc for citations).

설계 원칙 / Design principles:
  - 비례 제어 (P) + 데드밴드 — proportional control with deadband (PID 의 I/D 항은
    배수 시간이 길고 노이즈가 많은 바닥난방에 비효율).
  - 사이클당 최소 on / off 시간 — minimum on/off times per cycle (액추에이터·보일러
    수명 보호).
  - 셋포인트 근접 시 듀티 감소 — anti-overshoot duty reduction near setpoint.
  - 객실 간 phase staggering 없음 — no inter-room phase staggering (5객실 시스템에서는
    P-제어가 자체 보정함; 연구 §9 참조).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .const import LOGGER

if TYPE_CHECKING:
    from .iparkapp import BestinIparkAppAPI


# ---------------------------------------------------------------------------
# 프로파일 — Profiles (researched values; see PROTOCOL_FINDINGS / research file)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PwmProfile:
    """PWM 프로파일 — One PWM profile (Eco / Comfort / Boost)."""

    name: str
    cycle_period_s: int          # 한 사이클 길이 (초) — full cycle length
    proportional_band_c: float   # 비례 대역 (°C) — temp error → 100% duty span
    min_on_s: int                # 최소 on 시간 — minimum on time
    min_off_s: int               # 최소 off 시간 — minimum off time
    deadband_pct: float          # 듀티 변화 데드밴드 — duty change threshold
    overshoot_guard_c: float = 0.5
    overshoot_factor: float = 0.8


# 'off' 는 PWM 비활성 — 'off' means PWM disabled (passthrough to wallpad).
# 다른 키 이름은 HA preset_mode 와 옵션 플로우 양쪽에서 식별자로 사용됩니다.
# Other keys are used as identifiers in both HA preset_mode and the options flow.
PWM_PROFILES: dict[str, PwmProfile] = {
    "eco": PwmProfile(
        name="eco",
        cycle_period_s=20 * 60,
        proportional_band_c=2.5,
        min_on_s=120,
        min_off_s=90,
        deadband_pct=8.0,
    ),
    "comfort": PwmProfile(
        name="comfort",
        cycle_period_s=15 * 60,
        proportional_band_c=2.0,
        min_on_s=120,
        min_off_s=60,
        deadband_pct=5.0,
    ),
    "boost": PwmProfile(
        name="boost",
        cycle_period_s=10 * 60,
        proportional_band_c=1.5,
        min_on_s=120,
        min_off_s=30,
        deadband_pct=3.0,
    ),
}

PWM_OFF = "off"
PWM_VALID_MODES = (PWM_OFF, "eco", "comfort", "boost")
DEFAULT_PWM_MODE = PWM_OFF
TICK_INTERVAL_S = 30


# ---------------------------------------------------------------------------
# 객실별 상태 — Per-room state
# ---------------------------------------------------------------------------

@dataclass
class RoomPwmState:
    """객실 PWM 상태 — Per-room state tracked by the controller."""

    room: int
    setpoint: float = 22.0       # 사용자 의도 setpoint (HA 에서 설정)
    current_temp: float = 0.0    # 폴링으로 갱신 — updated from polling
    target_duty_pct: float = 0.0
    last_sent_phase: bool | None = None  # True = on, False = off, None = never
    cycle_started_at: datetime = field(default_factory=datetime.now)
    phase_started_at: datetime = field(default_factory=datetime.now)
    enabled: bool = True


# ---------------------------------------------------------------------------
# 컨트롤러 — Controller
# ---------------------------------------------------------------------------

class PwmController:
    """객실별 비례 PWM 컨트롤러 — Per-room proportional PWM controller.

    한 인스턴스가 모든 객실을 관리합니다. ``BestinIparkAppAPI`` 가 PWM 활성화 시
    인스턴스화하며, 폴링·명령 경로에 후크되어 동작합니다.

    A single instance manages all rooms. ``BestinIparkAppAPI`` instantiates one
    when PWM is enabled and routes polling reads + control writes through it.
    """

    def __init__(
        self,
        api: "BestinIparkAppAPI",
        profile_key: str,
    ) -> None:
        if profile_key == PWM_OFF or profile_key not in PWM_PROFILES:
            raise ValueError(f"PwmController requires an active profile, got {profile_key!r}")
        self.api = api
        self.profile_key = profile_key
        self.profile: PwmProfile = PWM_PROFILES[profile_key]
        self.rooms: dict[int, RoomPwmState] = {}
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
            "PWM 컨트롤러 시작 — PwmController started, profile=%s, cycle=%ds, band=%.1f°C",
            self.profile.name, self.profile.cycle_period_s, self.profile.proportional_band_c,
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

    # ----- public hooks ----------------------------------------------------

    def upsert_room(
        self,
        room: int,
        current_temp: float | None,
        polled_setpoint: float | None,
    ) -> None:
        """폴링 시 호출 — Called from polling. Adopts the wallpad's current setpoint
        the first time we see this room, then takes over."""
        st = self.rooms.get(room)
        if st is None:
            st = RoomPwmState(
                room=room,
                setpoint=polled_setpoint if polled_setpoint is not None else 22.0,
                current_temp=current_temp if current_temp is not None else 0.0,
            )
            self.rooms[room] = st
            LOGGER.debug(
                "PWM 객실 등록 — room %s adopted setpoint=%.1f, current=%.1f",
                room, st.setpoint, st.current_temp,
            )
            return
        if current_temp is not None:
            st.current_temp = current_temp

    def set_setpoint(self, room: int, setpoint: float) -> None:
        """사용자 setpoint 변경 — User changed the setpoint via HA."""
        st = self.rooms.get(room)
        if st is None:
            st = RoomPwmState(room=room, setpoint=setpoint)
            self.rooms[room] = st
        else:
            st.setpoint = setpoint
        LOGGER.info("PWM 객실 %s setpoint → %.1f°C", room, setpoint)

    def get_displayed_setpoint(self, room: int) -> float | None:
        """HA 에 표시할 setpoint — Returns the user-facing setpoint to show in HA
        (the wallpad's echoed value during PWM is manipulated and shouldn't be
        shown to the user)."""
        st = self.rooms.get(room)
        return st.setpoint if st else None

    def is_on(self, room: int) -> bool | None:
        """현재 PWM phase — Returns whether the controller currently has the
        wallpad on/off for this room (None if unknown)."""
        st = self.rooms.get(room)
        return st.last_sent_phase if st else None

    # ----- internal --------------------------------------------------------

    async def _run(self) -> None:
        """틱 루프 본체 — Tick loop body."""
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception as ex:  # noqa: BLE001
                LOGGER.exception("PWM tick error: %s", ex)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=TICK_INTERVAL_S
                )
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        now = datetime.now()
        for state in list(self.rooms.values()):
            if not state.enabled:
                continue
            duty = self._compute_duty(state)
            should_be_on = self._decide_phase(state, duty, now)
            if should_be_on == state.last_sent_phase:
                continue
            elapsed = (now - state.phase_started_at).total_seconds()
            if state.last_sent_phase is True and elapsed < self.profile.min_on_s:
                continue  # honour minimum on-time
            if state.last_sent_phase is False and elapsed < self.profile.min_off_s:
                continue  # honour minimum off-time
            await self._apply(state, should_be_on, now)
            state.target_duty_pct = duty

    def _compute_duty(self, state: RoomPwmState) -> float:
        """비례 + anti-overshoot — Proportional with anti-overshoot near setpoint."""
        error = state.setpoint - state.current_temp
        duty = max(0.0, min(100.0, (error / self.profile.proportional_band_c) * 100.0))
        # 셋포인트 근접 시 듀티 감소 — reduce duty when getting close to target.
        if 0 < error < self.profile.overshoot_guard_c and duty > 50.0:
            duty *= self.profile.overshoot_factor
        return duty

    def _decide_phase(
        self, state: RoomPwmState, duty: float, now: datetime
    ) -> bool:
        """현재 사이클 위치에서 on 이어야 하는지 판단 — Should the wallpad be on now?"""
        cycle_s = self.profile.cycle_period_s
        elapsed_in_cycle = (now - state.cycle_started_at).total_seconds()
        if elapsed_in_cycle >= cycle_s:
            # 사이클 갱신 — start a new cycle
            state.cycle_started_at = now
            elapsed_in_cycle = 0.0
        on_duration_s = cycle_s * (duty / 100.0)
        return elapsed_in_cycle < on_duration_s

    async def _apply(
        self, state: RoomPwmState, should_be_on: bool, now: datetime
    ) -> None:
        """월패드에 명령 전송 — Send the on/off command to the wallpad.

        On 시 setpoint 를 일시적으로 current+5 로 올려 월패드가 보일러를 호출하도록
        강제합니다. Off 시에는 사용자의 실제 setpoint 를 함께 보냅니다.
        On the on-pulse we briefly elevate the setpoint to current+5°C so the
        wallpad's onboard logic actually calls for heat. On the off-pulse we
        send the user's true setpoint so any external observer sees a sensible
        value at rest.
        """
        forced = state.current_temp + 5 if should_be_on else state.setpoint
        verb = "on" if should_be_on else "off"
        ctrl = f"{verb}/{forced:g}"
        LOGGER.debug(
            "PWM 객실 %s → %s (duty=%.1f%%, current=%.1f, setpoint=%.1f, sent=%s)",
            state.room, "ON" if should_be_on else "OFF", state.target_duty_pct,
            state.current_temp, state.setpoint, ctrl,
        )
        try:
            await self.api.send_temper_raw_command(state.room, ctrl)
        except Exception as ex:  # noqa: BLE001
            LOGGER.warning("PWM apply failed for room %s: %s", state.room, ex)
            return
        state.last_sent_phase = should_be_on
        state.phase_started_at = now
