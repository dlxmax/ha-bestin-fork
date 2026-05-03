# iPark 스마트홈 앱 연동 가이드 / iPark Smarthome App Integration Guide

이 옵션은 안드로이드 [iPark 스마트홈 앱](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet) 과 동일한 방식으로 단지의 중앙 PHP 서버 (예: `220.79.141.134`) 에 직접 통신합니다. 월패드 펌웨어가 RS-485 연결을 거부하거나, 클라우드(`center.hdc-smart.com`) 가 작동하지 않는 구형 단지에서 가장 잘 동작합니다.  
*This option talks directly to the apartment complex's central PHP server (e.g. `220.79.141.134`) using the same protocol as the official Android [iPark Smarthome app](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet). It works best for older complexes whose wallpads do not accept RS-485 from third-party adapters and where the official cloud (`center.hdc-smart.com`) does not respond.*

## 만들게 된 이유 / Why this option was added

본 포크 작성자의 가정에서는 두 가지 기존 방식이 모두 동작하지 않았습니다. 월패드가 RS-422 라인을 사용해 RS-485 어댑터로 신호 해석이 어려웠고, 같은 단지 서버 IP (예: `http://220.79.141.134/`) 의 웹사이트는 로그인은 되지만 모든 제어 명령이 응답 없이 사라졌습니다. 반면 안드로이드 iPark 스마트홈 앱은 같은 서버에서 정상적으로 조명을 켜고 끌 수 있었습니다. 앱을 분석한 결과, 앱은 웹사이트와 거의 동일한 호출을 보내지만 두 가지 차이가 있었습니다.  
*Both existing methods failed in this fork author's home. The wallpad uses RS-422 (not 485), so off-the-shelf RS-485 adapters could not parse the wallpad's frames; and the apartment-complex website (e.g. `http://220.79.141.134/`) accepted login but every control command vanished silently. The Android iPark Smarthome app worked fine against the same server. Static analysis of the APK revealed the app makes near-identical calls but with two critical differences:*

1. URL 경로가 `/webapp/data/...` 로 끝나야 합니다 (웹사이트 코드의 `/mobilehome/data/...` 가 아닙니다).  
   *URLs use `/webapp/data/...` (not `/mobilehome/data/...` like some website code paths).*
2. 모든 요청에 `X-Requested-With: XMLHttpRequest` 헤더가 반드시 포함되어야 합니다. 이 헤더가 없으면 서버는 즉시 `result="timeout"` 더미 응답을 돌려보냅니다 — 웹사이트가 무반응이었던 이유가 바로 이것이었습니다.  
   *Every request must carry `X-Requested-With: XMLHttpRequest`. Without it the server short-circuits with a stub `result="timeout"` — that is exactly why the website's controls silently dropped every command.*

이 두 가지 차이를 그대로 반영한 것이 본 'iPark 스마트홈 앱' 옵션입니다.  
*This new "iPark Smarthome App" option mirrors both differences faithfully, which is what makes it work in homes where the website-based methods don't.*

## 언제 이 옵션을 선택해야 하나요? / When should I pick this option?

- 안드로이드 iPark 스마트홈 앱은 정상 동작하지만, RS-485 어댑터로는 신호를 읽을 수 없거나 (예: RS-422 등 구형 라인) 클라우드 연동이 동작하지 않는 경우.  
  *The Android iPark Smarthome app works but RS-485 (or RS-422) adapters can't read your wallpad, or the cloud method doesn't connect.*
- 토큰 / UUID 복사·붙여넣기 없이 평소 사용하는 아이디·비밀번호로 연동하고 싶은 경우.  
  *You want to log in with the username/password you already use in the app — no UUID copy-paste.*
- 단지 중앙 서버 IP 를 직접 알 필요 없이 단지 이름만으로 설정하고 싶은 경우.  
  *You want to pick your apartment by name instead of looking up an IP.*

## 1단계: 통합구성요소 추가 / Step 1: Add the integration

1. **기기 및 서비스 → 통합구성요소 추가하기 → BESTIN** 검색.  
   ***Devices & Services → Add Integration → search for `BESTIN`.***
2. 메뉴에서 **iPark 스마트홈 앱 / iPark Smarthome App** 항목을 선택합니다.  
   *Pick **iPark Smarthome App** from the menu.*

## 2단계: 단지 선택 / Step 2: Pick your complex

i-parklife.com 디렉터리에서 60여 개 단지가 자동으로 조회됩니다.  
*The integration auto-fetches the ~60 complexes registered with i-parklife.com.*

- 드롭다운에서 단지 이름을 선택합니다 (예: `남양주 별내`).  
  *Pick your complex from the dropdown (e.g. `남양주 별내`).*
- 목록에 없거나 디렉터리 조회가 실패하면 **직접 입력 / Enter manually** 항목을 선택해 IP 주소를 직접 입력할 수 있습니다.  
  *If your complex isn't listed or the directory fetch fails, choose **Enter manually** and supply the server IP yourself.*

| 필드 / Field | 필수 / Required | 설명 / Description |
|---|---|---|
| `ip` | O | 단지 중앙 서버 IP — 일반적으로 단지 카탈로그에서 자동으로 채워집니다.<br>*Central server IP — auto-filled from the directory normally.* |
| `sitename` | × | 자유롭게 입력 — 통합 이름에 표시됩니다.<br>*Free-form — used in the integration title.* |
| `sitecode` / `weather` / `lat` / `lng` | × | 디렉터리에 있는 값 (있으면 그대로 사용).<br>*Pass-through directory values, optional.* |

## 3단계: 로그인 / Step 3: Sign in

| 필드 / Field | 설명 / Description |
|---|---|
| `username` | iPark 스마트홈 앱에서 사용하는 아이디.<br>*Same username as in the iPark Smarthome app.* |
| `password` | iPark 스마트홈 앱에서 사용하는 비밀번호.<br>*Same password as in the iPark Smarthome app.* |

토큰 / UUID 복사·붙여넣기는 필요 없습니다. 통합이 안드로이드 앱과 동일한 2단계 로그인을 자동으로 수행합니다.  
*No token or UUID copy-paste is required — the integration runs the same two-step login the Android app does.*

## 지원되는 기기 / Supported devices

| 기기 / Device | 동작 / Behavior |
|---|---|
| 거실 조명 / Living-room lights | 개별 ON/OFF (`switch1` ~ `switch6`)<br>*Per-switch ON/OFF for `switch1`..`switch6`.* |
| 각실 조명 / Per-room lights | 객실별 ON/OFF (단지에서 활성화된 경우)<br>*Per-room ON/OFF where the wallpad supports it.* |
| 콘센트 / Outlets | ON/OFF + 대기전력 자동차단 (`set` / `unset`)<br>*ON/OFF plus standby-cutoff (`set` / `unset`).* |
| 난방 / Thermostat | 객실별 ON/OFF + 목표온도 — `unit_cnt` 가 알려주는 객실만 climate 로 노출<br>*Per-room ON/OFF + setpoint, only for rooms reported in `unit_cnt`.* |
| 추가 비제어 난방 센서 / Extra uncontrollable heat sensor | `unit_cnt` 를 초과한 추가 'room' 응답은 읽기 전용 `heatsource` 센서로 노출됩니다. 정확한 의미는 단지마다 다르며, 지역난방 공급 온도일 가능성이 있으나 다른 출처일 수도 있습니다 (확인 안 됨).<br>*Any 'room' response beyond `unit_cnt` is exposed as a read-only `heatsource` sensor. The exact meaning varies by complex — it could be the district heating supply temperature, or it could be something else (we haven't confirmed).* |
| 가스밸브 / Gas valve | 닫기 전용 (앱과 동일)<br>*Close only — matches the official app.* |
| 환기 / Ventilation | ON/OFF + 풍량 (low / mid / high)<br>*ON/OFF + speed (low / mid / high).* |
| 외출 모드 / Away mode | 'unoccupied' 설정 (앱과 동일)<br>*Sets `unoccupied` — matches the app.* |
| 도어락 / Door lock | 상태 표시만 (앱과 동일 — 제어 명령은 앱에서도 제공되지 않습니다)<br>*Status only — the app itself doesn't expose remote control.* |
| 에너지 모니터링 / Energy monitoring | 월별 평균 사용량 — 전기 / 가스 / 난방 / 온수 / 수도, 단지 평균과 본 세대 각각.<br>*Monthly average usage — Electric / Gas / Heat / Hot water / Water, with both complex average and your household.* |

## 의도적으로 제외된 항목 / Intentionally skipped

다음 항목은 앱에 있지만 통합에서는 제외했습니다 (필요하면 이슈 등록).  
*The following are present in the app but intentionally not exposed (open an issue if you want them):*

- 공지사항 / 자유게시판 / 설문조사 / 방문자 확인 / 택배 정보  
  *Notices / boards / polls / visitor logs / parcel logs.*
- 앱 내 일기예보 — 일부 단지에서 데이터가 오래되어 있습니다.  
  *In-app weather forecast — stale on some complexes.*

## 동작 원리 (요약) / How it works (in brief)

1. 단지 디렉터리(`http://www.i-parklife.com/service/getSiteIPARKList.php?is_utf=1`) 에서 단지 IP 와 SITE 메타데이터를 가져옵니다.  
   *Fetches the complex IP and SITE metadata from the i-parklife.com directory.*
2. 2단계 로그인으로 `PHPSESSID` 쿠키를 획득합니다.  
   *Performs the 2-step login to obtain the `PHPSESSID` cookie.*
3. `index.php` 를 한 번 로드해 월패드 IPC 채널을 활성화합니다.  
   *Loads `index.php` once to prime the wallpad's IPC channel.*
4. 모든 장치 클래스를 폴링합니다 (`getHomeDevice.php`, 난방은 `getHomeDevice_heat.php`).  
   *Polls every device class via `getHomeDevice.php` (heat uses the separate `getHomeDevice_heat.php`).*
5. 모든 요청에 `X-Requested-With: XMLHttpRequest` 헤더를 포함합니다 — 이 헤더가 없으면 서버는 즉시 `result="timeout"` 더미 응답을 반환합니다.  
   *Sends `X-Requested-With: XMLHttpRequest` on every request — without it the server short-circuits with a stub `result="timeout"`.*

## 알려진 제한 사항 / Known limitations

- 단지 중앙 서버는 PHP 4.4.9 / IIS 7.0 등 매우 오래된 환경에서 동작합니다. 단지마다 펌웨어 차이가 있어, 일부 기기 클래스는 동작하지 않을 수 있습니다 (예: 본 테스트 세대에서는 가스밸브가 `result="fail"` 반환).  
  *The central server runs ancient PHP 4.4.9 on IIS 7.0; firmware varies between complexes so some device classes may be unavailable on certain households (e.g. gas valve returned `result="fail"` on the test household).*
- 단지 디렉터리의 일부 항목에서 `LAT` / `LNG` 필드가 서로 뒤바뀌어 있습니다. 통합은 앱과 동일하게 그 값을 그대로 전달합니다.  
  *Some directory entries have their `LAT` and `LNG` fields swapped. The integration passes them through verbatim, exactly like the app.*
- 도어락은 상태만 노출됩니다. 앱 자체가 원격 잠금/해제를 제공하지 않으므로 통합도 동일합니다.  
  *Door locks are status-only because the app itself does not expose remote lock/unlock.*

## PWM 제어 / PWM control

월패드의 객실별 이진 on/off + setpoint 만으로는 바닥난방의 큰 열관성에 비해 너무 거친 제어가 됩니다. v1.4 부터 각 온도조절기가 표준 HA **프리셋 (preset_mode)** 을 객실별로 노출합니다. iPark 스마트홈 앱 옵션에서는 프리셋이 슬로우 PWM 사이클을 함께 트리거합니다 (다른 게이트웨이는 setpoint 만 변경됩니다).  
*The wallpad's per-room binary on/off + setpoint is too coarse for high-thermal-mass radiant floors. From v1.4, each thermostat exposes the standard HA **preset_mode** dropdown per room. On the iPark Smarthome App option, presets also trigger a slow PWM cycle (on the other gateways, presets just change the setpoint).*

### 핵심 결론 / Key takeaways

1. **프리셋은 표준 HA 인터페이스입니다** — Climate 카드의 'Preset' 드롭다운, `climate.set_preset_mode` 서비스, 음성 명령 ("거실을 외출 모드로") 모두 지원합니다.  
   *Presets are standard HA — climate-card dropdown, `climate.set_preset_mode` service, and voice commands ("set the living room to away mode") all just work.*
2. **객실마다 다른 프리셋 가능** — 침실은 Sleep, 거실은 Comfort.  
   *Per-room presets — bedroom on Sleep while living room stays on Comfort.*
3. **휴가 일정은 서비스 호출로** — `bestin.set_vacation_window` 가 시작·복귀 시각을 받아 자동으로 프리셋을 전환합니다.  
   *Vacation date scheduling via `bestin.set_vacation_window` — pass start + end datetimes; presets transition automatically.*
4. **솔직한 경제성**: PWM 의 순수한 절감 효과는 5-15% 범위, 통상 8-12% 정도. 핵심 절감 동력은 PWM 자체보다 **PWM 덕분에 야간 setback 을 실용적으로 사용할 수 있게 되는 점** 입니다. 자세한 수치는 §11 (로컬 연구 파일) 참조.  
   *Honest economics: pure PWM savings land at 5-15 % (typically 8-12 %). The bigger lever is **PWM making night setback practical** — it's the setback that saves money, PWM just removes the slow-recovery pain. Full numbers in research file §11.*

### 프리셋 / Presets

| 프리셋 / Preset | 셋포인트 / Setpoint | PWM 사이클 / Cycle (iparkapp only) | 용도 / Use case | 절감 (vs 22°C 항시) / Savings vs 22°C continuous |
|---|---|---|---|---|
| **None** _(기본 / default)_ | 사용자 지정 / user | — (passthrough) | PWM 없음. 월패드 기본 동작. / No PWM; wallpad default. | 0 % |
| **Comfort / 쾌적** | 22°C | 15 분 / min | 활동 시간대. / Active occupancy. | baseline |
| **Eco / 에코** | 20°C | 20 분 / min | 절감 우선. / Cost-conscious. | -3 to -5 % |
| **Sleep / 수면** | 17°C | 25 분 / min | 야간 8-10 시간. 8시간 OFF 보다 안전 + 효율. / Overnight 8-10 h. Safer & more efficient than full-off. | -10 to -15 % |
| **Away / 외출** | 16°C | 25 분 / min | 출근·짧은 외출. / Work day or short trip. | -8 to -12 % |
| **Vacation / 휴가** | 13°C | 30 분 / min | 다일 부재 (7-14일). / Multi-day absence. | -20 to -30 % |
| **Frost / 결빙방지** | 9°C | 30 분 / min | 장기 미사용 / 동결방지. / Long unoccupied / pipe protection. | -40 to -50 % |
| **Boost** | 23°C | 10 분 / min | 휴가 복귀 후 빠른 가열. **상시 사용 비권장** (밸브 마모). / Post-vacation recovery. **Not for daily use** (valve wear). | n/a (recovery) |

> **8시간 완전 OFF 습관에 대해 / On the "8 hours fully off" habit:** 안전하지만 최적은 아닙니다. 바닥이 너무 식으면 아침 회복 에너지가 절감을 상쇄하고, 차가운 바닥에 결로가 생길 수 있습니다. **Sleep 모드 (17°C)** 가 같은 8시간 동안 더 적은 에너지를 쓰면서 아침에 빠르게 회복합니다.  
> *Safe but not optimal. Letting the floor get too cold means morning rebound energy cancels the savings, and the cold floor can develop condensation. **Sleep mode (17 °C)** uses less energy over the same 8 hours and recovers faster in the morning.*

### 시스템 LPM 밸브 권장 설정 / Recommended system LPM valve setting **(중요 / important)**

본 통합이 설치된 단지의 일반적인 구성은 단지 1개의 시스템 전체용 수동 유량 밸브 (LPM, 분당 리터) 가 모든 객실 분배기 앞단에 있습니다. **PWM 사용 시 이 밸브를 다시 조정해야 합니다.**  
*Most ondol systems have a single manual system-wide flow valve (LPM, litres-per-minute) upstream of all room manifolds. **When using PWM you must re-adjust it.***

- **기존 'low flow' 위치보다 약 3-4 배 열기** — 또는 60-80 m² 5객실 아파트 기준 **8-12 LPM 부근**. 밸브 표시가 LPM 이 아닌 단순 단계라면 'high' 위치 근처.  
  *Open it to **roughly 3-4× your old "low" position**, or about **8-12 LPM** for a 60-80 m² 5-room apartment. Near 'high' if the valve isn't LPM-marked.*
- **왜:** PWM 은 동일 에너지를 더 짧은 펄스로 전달합니다. 펄스 동안의 유량 = 연속 운전 유량 ÷ 평균 듀티. 평균 듀티가 25-30 % 면 3-4× 가 등가 유량입니다.  
  *Why: PWM compresses the same total energy into shorter pulses; per-pulse flow = continuous-flow ÷ average duty. At 25-30 % average duty, 3-4× is the equivalent flow.*
- **커미셔닝:** Comfort (또는 Sleep) 로 추운 주말을 지내며 객실별 평균 듀티와 온도 변동을 HA 히스토리로 관찰. 평균 듀티 ≥ 80 % 인데 셋포인트 미달이면 → 더 열기. 평균 듀티 ≤ 30 % 인데 과열이면 → 다시 조이기.  
  *Commissioning: run a cold weekend on Comfort (or Sleep) and watch the per-room average duty + temperature variance in HA history. Average duty ≥ 80 % AND undershoot → open further. Average duty ≤ 30 % AND overshoot → close down.*

LPM 밸브 위치를 잘못 설정하면 PWM 의 효과가 크게 떨어집니다. 통합 설정 화면 (Settings → Devices & Services → BESTIN → Configure) 의 안내문에도 같은 권장사항이 있습니다.  
*Wrong LPM position significantly degrades PWM effectiveness. The same advice appears in the integration's options-flow description.*

### 자동화 / Automations — Blueprints

반복 일정 (야간 setback / 외출 / 휴가) 은 HA Blueprint 로 제공합니다. 한 번 임포트한 후 HA UI 에서 객실·시각·도우미를 채우면 됩니다 — 통합 안에 별도 UI 를 만들지 않은 이유는 HA 가 이미 훌륭한 UI 를 제공하기 때문입니다.  
*Recurring schedules (night setback / away / vacation) are shipped as HA Blueprints. Import once, then fill in entity IDs / times / helpers via HA's standard UI — we don't reinvent it because HA already has a polished one.*

#### 야간 setback / Night setback

매일 정해진 시각에 Sleep → Boost → Comfort 로 자동 전환. 평일/주말 토글 포함.  
*Daily Sleep → Boost → Comfort transitions; optional weekday-only toggle.*

[![Open in HA / HA 에서 열기](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdlxmax%2Fha-bestin-fork%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fbestin%2Fnight_setback.yaml)

#### 휴가 일정 / Vacation window

`input_datetime` helper 두 개 (출발 시각 · 복귀 시각) 를 만든 뒤 임포트. 복귀 N 시간 전 Boost 설정 가능.  
*Create two `input_datetime` helpers (depart, return), then import. Optional pre-warm hours before return.*

[![Open in HA / HA 에서 열기](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdlxmax%2Fha-bestin-fork%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fbestin%2Fvacation_window.yaml)

#### 외출 자동 감지 / Away when home is empty

가족 모두 not_home → Away. 누군가 home → Comfort. HA 의 person/device_tracker 엔티티 사용.  
*Triggers on HA presence entities — all not_home → Away; any home → Comfort.*

[![Open in HA / HA 에서 열기](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdlxmax%2Fha-bestin-fork%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fbestin%2Faway_when_empty.yaml)

세 blueprint 모두 표준 `climate.set_preset_mode` 서비스를 사용하므로 다른 thermostat 통합과도 함께 동작합니다 (entity_id 만 본인 환경에 맞게 지정).  
*All three blueprints use the standard `climate.set_preset_mode` service, so they also work alongside any other HA-thermostat integration — just point them at the right entity_ids.*

원본 YAML: [blueprints/automation/bestin/](https://github.com/dlxmax/ha-bestin-fork/tree/main/blueprints/automation/bestin)  
*Raw YAML files: [blueprints/automation/bestin/](https://github.com/dlxmax/ha-bestin-fork/tree/main/blueprints/automation/bestin)*

### 알고리즘 / Algorithm (참고 / reference)

iparkapp 게이트웨이에서 활성 프리셋이 PWM 을 트리거할 때:

```
temp_error = user_setpoint - current_temp
duty% = clamp(0, 100, (temp_error / proportional_band) × 100)
if 0 < temp_error < 0.5°C and duty > 50%:
    duty *= 0.8   # 셋포인트 근접 시 듀티 감소 / anti-overshoot near setpoint
```

추가 제약 / additional constraints: 프리셋별 최소 on / off 시간 (밸브·보일러 보호), 듀티 변화 데드밴드 (채터 방지). 자세한 수치는 `pwm.py` 의 `PRESET_PROFILES` 참조.  
*See `PRESET_PROFILES` in `pwm.py` for the exact numbers.*

근거 / Sources: IEA ECES Task 32 (2018), ASHRAE HVAC Applications (2019), EN 12531, VDI 6030, OJ Electronics OCD5, Honeywell Bulletin 41-353, Uponor Design Guide (2020). 전체 인용 + 경제성 분석 + 밸브 수명 분석은 로컬 연구 파일 (`temp/research/ondol_pwm_research.md`, gitignored) 참조.  
*Full citations + economics + valve-lifetime analysis in the local research file (`temp/research/ondol_pwm_research.md`, gitignored).*

### 알려진 제한 / Known caveats

- **월패드 setpoint 가 일시적으로 조작됩니다 (PWM 활성 객실 한정).** ON 펄스 동안 월패드 화면에는 사용자 값보다 높은 setpoint 가 잠시 표시됩니다 — 월패드의 내장 임계값을 강제로 통과시키기 위함입니다. HA UI 는 항상 사용자의 실제 의도값을 보여줍니다.  
  *Wallpad setpoint is momentarily manipulated on PWM-active rooms — during the ON pulse the wallpad face shows a setpoint elevated above your true target (forces the wallpad's onboard threshold to call for heat). HA always displays your real value.*
- **HA 재시작.** PWM 컨트롤러 상태는 메모리에만 보관됩니다. 재시작 후 첫 폴링에서 월패드의 (조작된) echo 를 임시로 채택할 수 있으니, 재시작 직후 한 번 프리셋이나 setpoint 를 다시 적용해 주세요.  
  *HA restart clears in-memory PWM state. Re-apply preset or setpoint once after restart.*
- **다른 가족이 월패드를 직접 조작하면**, 다음 폴링에서 그 값이 PWM 컨트롤러로 흡수됩니다. 의도된 값이 아니면 HA 에서 다시 설정.  
  *If someone changes the setpoint at the wallpad directly, the next poll adopts it. Re-set in HA if not desired.*
- **밸브 수명 vs 절감.** PWM 은 분배기 액추에이터 사이클을 약 5-10 배 늘려 통상 수명을 단축합니다 (대략 약 5-8년). 본 통합의 기본값 (None — PWM 비활성) 을 유지하면 마모 가속이 없습니다. 자세한 분석은 연구 파일 §10.  
  *PWM accelerates manifold actuator cycling ~5-10×, shortening typical life to roughly 5-8 years. Default (None — PWM off) avoids the wear. Full analysis in research file §10.*

## 디버깅 / Debugging

문제가 있는 경우 `configuration.yaml` 에 아래 내용을 추가하고 HA 를 재시작하면 상세 로그를 얻을 수 있습니다.  
*If something doesn't work, add the snippet below to `configuration.yaml` and restart HA to get verbose logs.*

```yaml
logger:
  default: info
  logs:
    custom_components.bestin: debug
```
