# iPark 스마트홈 앱 연동 가이드 / iPark Smarthome App Integration Guide

이 옵션은 안드로이드 [iPark 스마트홈 앱](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet) 과 같은 방식으로 단지의 중앙 PHP 서버 (예: `203.0.113.10`) 와 직접 통신해요. 월패드 펌웨어가 RS-485 연결을 거부하거나, 클라우드(`center.hdc-smart.com`) 가 동작하지 않는 구형 단지에서 가장 잘 맞아요.  
*This option talks directly to the apartment complex's central PHP server (e.g. `203.0.113.10`) using the same protocol as the official Android [iPark Smarthome app](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet). It works best for older complexes whose wallpads do not accept RS-485 from third-party adapters and where the official cloud (`center.hdc-smart.com`) does not respond.*

## 만들게 된 이유 / Why this option was added

이 포크 작성자의 집에서는 기존 두 방식이 모두 동작하지 않았어요. 월패드가 RS-422 라인을 사용해 RS-485 어댑터로 신호 해석이 어려웠고, 같은 단지 서버 IP (예: `http://203.0.113.10/`) 의 웹사이트는 로그인은 되지만 모든 제어 명령이 응답 없이 사라졌어요. 반면 안드로이드 iPark 스마트홈 앱은 같은 서버에서 조명을 잘 켜고 끌 수 있었어요. 앱을 분석해 보니, 앱은 웹사이트와 거의 같은 호출을 보내지만 두 가지 차이가 있었어요.  
*Both existing methods failed in this fork author's home. The wallpad uses RS-422 (not 485), so off-the-shelf RS-485 adapters could not parse the wallpad's frames; and the apartment-complex website (e.g. `http://203.0.113.10/`) accepted login but every control command vanished silently. The Android iPark Smarthome app worked fine against the same server. Static analysis of the APK revealed the app makes near-identical calls but with two critical differences:*

1. URL 경로가 `/webapp/data/...` 로 끝나야 해요 (웹사이트 코드의 `/mobilehome/data/...` 가 아니에요).  
   *URLs use `/webapp/data/...` (not `/mobilehome/data/...` like some website code paths).*
2. 모든 요청에 `X-Requested-With: XMLHttpRequest` 헤더가 꼭 들어가야 해요. 이 헤더가 없으면 서버는 바로 `result="timeout"` 더미 응답을 돌려보내요. 웹사이트가 무반응이었던 이유가 바로 이거였어요.  
   *Every request must carry `X-Requested-With: XMLHttpRequest`. Without it the server short-circuits with a stub `result="timeout"` — that is exactly why the website's controls silently dropped every command.*

이 두 차이를 그대로 반영한 것이 'iPark 스마트홈 앱' 옵션이에요.  
*This new "iPark Smarthome App" option mirrors both differences faithfully, which is what makes it work in homes where the website-based methods don't.*

## 언제 이 옵션을 선택해야 하나요? / When should I pick this option?

- 안드로이드 iPark 스마트홈 앱은 정상 동작하지만, RS-485 어댑터로는 신호를 읽을 수 없거나 (예: RS-422 등 구형 라인) 클라우드 연동이 동작하지 않는 경우.  
  *The Android iPark Smarthome app works but RS-485 (or RS-422) adapters can't read your wallpad, or the cloud method doesn't connect.*
- 토큰 / UUID 복사·붙여넣기 없이 평소 사용하는 아이디·비밀번호로 연동하고 싶은 경우.  
  *You want to log in with the username/password you already use in the app — no UUID copy-paste.*
- 단지 중앙 서버 IP 를 직접 알 필요 없이 단지 이름만으로 설정하고 싶은 경우.  
  *You want to pick your apartment by name instead of looking up an IP.*

## 1단계: 통합구성요소 추가 / Step 1: Add the integration

1. **기기 및 서비스 → 통합구성요소 추가하기** 에서 **BESTIN** 을 검색하세요.  
   ***Devices & Services → Add Integration → search for `BESTIN`.***
2. 메뉴에서 **iPark 스마트홈 앱 / iPark Smarthome App** 항목을 고르세요.  
   *Pick **iPark Smarthome App** from the menu.*

## 2단계: 단지 선택 / Step 2: Pick your complex

i-parklife.com 디렉터리에서 60여 개 단지를 자동으로 가져와요.  
*The integration auto-fetches the ~60 complexes registered with i-parklife.com.*

- 드롭다운에서 단지 이름을 고르세요 (예: `남양주 별내`).  
  *Pick your complex from the dropdown (e.g. `남양주 별내`).*
- 목록에 없거나 디렉터리 조회가 실패하면 **직접 입력 / Enter manually** 항목을 골라 IP 주소를 직접 입력할 수 있어요.  
  *If your complex isn't listed or the directory fetch fails, choose **Enter manually** and supply the server IP yourself.*

| 필드 / Field | 필수 / Required | 설명 / Description |
|---|---|---|
| `ip` | O | 단지 중앙 서버 IP. 보통은 단지 목록에서 자동으로 채워져요.<br>*Central server IP — auto-filled from the directory normally.* |
| `sitename` | × | 자유롭게 입력하세요. 통합 이름에 표시돼요.<br>*Free-form — used in the integration title.* |
| `sitecode` / `weather` / `lat` / `lng` | × | 디렉터리에 있는 값 (있으면 그대로 사용).<br>*Pass-through directory values, optional.* |

## 3단계: 로그인 / Step 3: Sign in

| 필드 / Field | 설명 / Description |
|---|---|
| `username` | iPark 스마트홈 앱에서 사용하는 아이디.<br>*Same username as in the iPark Smarthome app.* |
| `password` | iPark 스마트홈 앱에서 사용하는 비밀번호.<br>*Same password as in the iPark Smarthome app.* |

토큰 / UUID 를 복사해 붙여 넣을 필요는 없어요. 통합이 안드로이드 앱과 같은 2단계 로그인을 자동으로 해요.  
*No token or UUID copy-paste is required — the integration runs the same two-step login the Android app does.*

## 지원되는 기기 / Supported devices

| 기기 / Device | 동작 / Behavior |
|---|---|
| 거실 조명 / Living-room lights | 개별 ON/OFF (`switch1` ~ `switch6`)<br>*Per-switch ON/OFF for `switch1`..`switch6`.* |
| 각실 조명 / Per-room lights | 객실별 ON/OFF (단지에서 활성화된 경우)<br>*Per-room ON/OFF where the wallpad supports it.* |
| 콘센트 / Outlets | ON/OFF + 대기전력 자동차단 (`set` / `unset`)<br>*ON/OFF plus standby-cutoff (`set` / `unset`).* |
| 난방 / Thermostat | 객실별 ON/OFF + 목표온도. `unit_cnt` 가 알려주는 객실만 climate 로 보여 줘요<br>*Per-room ON/OFF + setpoint, only for rooms reported in `unit_cnt`.* |
| 추가 비제어 난방 값 / Extra uncontrollable heat reading | `unit_cnt` 를 초과한 'room' 응답은 **보여 주지 않아요** (v1.4.11). v1.4.3~v1.4.10 은 이를 'Heating supply' 센서로 보여 줬지만 그 해석은 추측이었고, 실제 기기에서 63 °C 에 고정된 채 전혀 움직이지 않았어요. 값은 디버그 로그에만 남아요.<br>*A 'room' response beyond `unit_cnt` is **not exposed** (v1.4.11). v1.4.3–v1.4.10 surfaced it as a "Heating supply" sensor, but that reading was a guess and on real hardware it stays pinned at a constant 63 °C. It is now debug-logged only.* |
| 가스밸브 / Gas valve | 닫기 전용 (앱과 같아요)<br>*Close only — matches the official app.* |
| 환기 / Ventilation | ON/OFF + 풍량 (low / mid / high)<br>*ON/OFF + speed (low / mid / high).* |
| 외출 모드 / Away mode | 'unoccupied' 설정 (앱과 동일)<br>*Sets `unoccupied` — matches the app.* |
| 도어락 / Door lock | 상태 표시만 (앱과 같아요. 앱에서도 제어할 수 없어요)<br>*Status only — the app itself doesn't expose remote control.* |
| 에너지 모니터링 / Energy monitoring | 월별 평균 사용량: 전기 / 가스 / 난방 / 온수 / 수도, 본 세대와 단지 평균 각각. 항목명이 먼저 오고 단지 평균에 `(neighbor avg)` 가 붙어서 (`Gas` / `Gas (neighbor avg)`), 기기 카드에서 두 값이 항상 나란히 놓여요.<br>*Monthly average usage — Electric / Gas / Heat / Hot water / Water, for your household and the complex average. Names lead with the commodity and suffix the average with `(neighbor avg)` (`Gas` / `Gas (neighbor avg)`) so each pair sorts side by side on the device card.* |

## 의도적으로 제외된 항목 / Intentionally skipped

다음 항목은 앱에 있지만 통합에서는 뺐어요 (필요하면 이슈를 올려 주세요).  
*The following are present in the app but intentionally not exposed (open an issue if you want them):*

- 공지사항 / 자유게시판 / 설문조사 / 방문자 확인 / 택배 정보  
  *Notices / boards / polls / visitor logs / parcel logs.*
- 앱 안의 일기예보: 일부 단지에서는 데이터가 오래됐어요.  
  *In-app weather forecast — stale on some complexes.*

## 동작 원리 (요약) / How it works (in brief)

1. 단지 디렉터리(`http://www.i-parklife.com/service/getSiteIPARKList.php?is_utf=1`) 에서 단지 IP 와 SITE 메타데이터를 가져와요.  
   *Fetches the complex IP and SITE metadata from the i-parklife.com directory.*
2. 2단계 로그인으로 `PHPSESSID` 쿠키를 받아요.  
   *Performs the 2-step login to obtain the `PHPSESSID` cookie.*
3. `index.php` 를 한 번 로드해 월패드 IPC 채널을 깨워요.  
   *Loads `index.php` once to prime the wallpad's IPC channel.*
4. 모든 장치 클래스를 조회해요 (`getHomeDevice.php`, 난방은 `getHomeDevice_heat.php`).  
   *Polls every device class via `getHomeDevice.php` (heat uses the separate `getHomeDevice_heat.php`).*
   폴링 주기 (v1.4.15): 조명·환기·외출·도어락은 60초 (옵션에서 변경), 난방은 방마다 켜진 방은 5분 (꺼진 방은 30분), 에너지는 HA 시작 시 한 번 그리고 매시 10분. 세대에 없는 장치나 객실은 연속 5회 실패하면 약 1시간에 한 번만 다시 물어요.  
   *Poll schedule (v1.4.15): lights, ventilation, away mode and door lock every 60 s (changeable in the options), thermostats room by room, every 5 min for a room that is on (every 30 min for one that is off), energy once at HA start and then at 10 minutes past each hour. A device or room the home doesn't have is asked about only about once an hour after 5 failures in a row.*
5. 모든 요청에 `X-Requested-With: XMLHttpRequest` 헤더를 넣어요. 이 헤더가 없으면 서버는 바로 `result="timeout"` 더미 응답을 돌려줘요.  
   *Sends `X-Requested-With: XMLHttpRequest` on every request — without it the server short-circuits with a stub `result="timeout"`.*

## 알려진 제한 사항 / Known limitations

- 단지 중앙 서버는 PHP 4.4.9 / IIS 7.0 등 아주 오래된 환경에서 돌아가요. 단지마다 펌웨어가 달라서 일부 기기 클래스는 동작하지 않을 수 있어요 (예: 이 테스트 세대에서는 가스밸브가 `result="fail"` 을 돌려줘요).  
  *The central server runs ancient PHP 4.4.9 on IIS 7.0; firmware varies between complexes so some device classes may be unavailable on certain households (e.g. gas valve returned `result="fail"` on the test household).*
- 단지 디렉터리의 일부 항목에서 `LAT` / `LNG` 필드가 서로 뒤바뀌어 있어요. 통합은 앱과 똑같이 그 값을 그대로 넘겨요.  
  *Some directory entries have their `LAT` and `LNG` fields swapped. The integration passes them through verbatim, exactly like the app.*
- 도어락은 상태만 보여 줘요. 앱 자체가 원격 잠금/해제를 지원하지 않아서 통합도 같아요.  
  *Door locks are status-only because the app itself does not expose remote lock/unlock.*

## 슬로우 듀티 사이클 제어 / Slow duty-cycle control

> 명명 노트 / naming note: 우리가 적용하는 것은 분 단위 주기의 **시간 비례 (time-proportional) 슬로우 듀티 사이클** 이에요. 빠른 PWM 이 아니에요. 이전 버전에서 "PWM" 이라고 부르던 기능과 같아요 (v1.4.8 에서 이름만 정리했어요).  
> *What we apply is a **minutes-scale time-proportional duty cycle**, not the high-frequency PWM the word usually evokes. Same mechanism the docs previously called "PWM" — v1.4.8 only renamed the term.*

월패드의 객실별 이진 on/off + setpoint 만으로는 바닥난방의 큰 열관성에 비해 너무 거친 제어가 돼요. v1.4 부터 각 온도조절기가 표준 HA **프리셋 (preset_mode)** 을 방마다 제공해요. iPark 스마트홈 앱 옵션에서는 프리셋이 슬로우 듀티 사이클도 함께 켜요 (다른 게이트웨이는 setpoint 만 바꿔요).  
*The wallpad's per-room binary on/off + setpoint is too coarse for high-thermal-mass radiant floors. From v1.4, each thermostat exposes the standard HA **preset_mode** dropdown per room. On the iPark Smarthome App option, presets also trigger a slow duty-cycle (time-proportional) modulation (on the other gateways, presets just change the setpoint).*

### 핵심 결론 / Key takeaways

1. **프리셋은 표준 HA 인터페이스예요.** Climate 카드의 'Preset' 드롭다운, `climate.set_preset_mode` 서비스, 음성 명령 ("거실을 외출 모드로") 모두 돼요.  
   *Presets are standard HA — climate-card dropdown, `climate.set_preset_mode` service, and voice commands ("set the living room to away mode") all just work.*
2. **방마다 다른 프리셋을 쓸 수 있어요.** 침실은 Sleep, 거실은 Comfort 처럼요.  
   *Per-room presets — bedroom on Sleep while living room stays on Comfort.*
3. **휴가 일정은 서비스 호출로 해요.** `bestin.set_vacation_window` 가 시작·복귀 시각을 받아 자동으로 프리셋을 바꿔요.  
   *Vacation date scheduling via `bestin.set_vacation_window` — pass start + end datetimes; presets transition automatically.*
4. **절감 효과는 아직 측정하지 않았어요.** 이전 버전의 이 문서는 "5-15 % 절감" 같은 수치와 여러 표준·문헌을 근거로 들었지만, 그 연구 파일은 AI 가 썼고 검증되지 않았으며 일부 인용은 실제로 없는 자료예요. 확실한 건 물리 법칙뿐이에요: 실내 평균 온도를 낮추면 (야간 setback 포함) 항상 열이 덜 들어요. 바닥 축열이 크면 절감 폭이 줄고 회복이 느릴 뿐, 회복 난방이 절감을 "상쇄" 하지는 않아요. 난방비가 유량 (m³) 으로 나오는 세대는 HA 의 난방 검침 센서로 직접 비교해 보는 게 가장 확실해요.  
   *Savings have not been measured. Earlier versions of this page quoted "5-15 % savings" and a list of standards and papers, but that research file was written by an AI, never verified, and some of its citations don't exist. What is certain is physics: a lower average indoor temperature, night setback included, always uses less heat. A heavy floor makes the saving smaller and recovery slower; recovery does not "cancel" the saving. If your heating is billed by volume (m³), compare with the heating meter sensor in HA.*

### 프리셋 / Presets

| 프리셋 / Preset | 셋포인트 / Setpoint | 듀티 사이클 주기 / Cycle (iparkapp only) | 용도 / Use case |
|---|---|---|---|
| **None** _(기본 / default)_ | 사용자 지정 / user | 없음 / none (passthrough) | 듀티 사이클 없음. 월패드 기본 동작. / No duty cycling; wallpad default. |
| **Comfort / 쾌적** | 22°C | 15 분 / min | 활동 시간대. / Active occupancy. |
| **Eco / 에코** | 20°C | 20 분 / min | 절감 우선. / Cost-conscious. |
| **Sleep / 수면** | 17°C | 25 분 / min | 야간. / Overnight. |
| **Away / 외출** | 16°C | 25 분 / min | 출근·짧은 외출. / Work day or short trip. |
| **Vacation / 휴가** | 13°C | 30 분 / min | 여러 날 부재. / Multi-day absence. |
| **Frost / 결빙방지** | 9°C | 30 분 / min | 장기 미사용. / Long unoccupied. |
| **Boost** | 23°C | 10 분 / min | 빠른 가열. 펄스가 잦아서 늘 쓰는 건 권하지 않아요. / Fast warm-up. Pulses often, so not for daily use. |

> **밤새 끄기 vs Sleep 프리셋 / Off overnight vs the Sleep preset:** 완전히 끄는 쪽이 열은 가장 적게 써요. 대신 바닥이 많이 식어서 아침에 회복하는 데 몇 시간 걸려요. Sleep (17°C) 은 열을 조금 더 쓰는 대신 아침에 덜 추워요. 어느 쪽이 나은지는 비용이 아니라 쾌적함의 문제예요.  
> *Turning the heat fully off overnight uses the least heat, but the floor cools further and takes hours to recover. Sleep (17 °C) uses a little more heat and leaves the morning less cold. Which is better is a comfort question, not a cost one.*

### 자동화 / Automations: Blueprints

반복 일정 (야간 setback / 외출 / 휴가) 은 HA Blueprint 로 제공해요. 한 번 가져온 뒤 HA UI 에서 객실·시각·도우미를 채우면 돼요. 통합 안에 따로 UI 를 만들지 않은 건 HA 에 이미 좋은 UI 가 있어서예요.  
*Recurring schedules (night setback / away / vacation) are shipped as HA Blueprints. Import once, then fill in entity IDs / times / helpers via HA's standard UI — we don't reinvent it because HA already has a polished one.*

#### 야간 setback / Night setback

매일 정해진 시각에 Sleep → Boost → Comfort 로 자동으로 바꿔요. 평일/주말 토글도 있어요.  
*Daily Sleep → Boost → Comfort transitions; optional weekday-only toggle.*

[![Open in HA / HA 에서 열기](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdlxmax%2Fha-bestin-fork%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fbestin%2Fnight_setback.yaml)

#### 휴가 일정 / Vacation window

`input_datetime` helper 두 개 (출발 시각 · 복귀 시각) 를 만든 뒤 가져오세요. 복귀 N 시간 전에 Boost 를 걸 수도 있어요.  
*Create two `input_datetime` helpers (depart, return), then import. Optional pre-warm hours before return.*

[![Open in HA / HA 에서 열기](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdlxmax%2Fha-bestin-fork%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fbestin%2Fvacation_window.yaml)

#### 외출 자동 감지 / Away when home is empty

가족 모두 not_home → Away. 누군가 home → Comfort. HA 의 person/device_tracker 엔티티를 써요.  
*Triggers on HA presence entities — all not_home → Away; any home → Comfort.*

[![Open in HA / HA 에서 열기](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdlxmax%2Fha-bestin-fork%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fbestin%2Faway_when_empty.yaml)

세 blueprint 모두 표준 `climate.set_preset_mode` 서비스를 쓰기 때문에 다른 thermostat 통합과도 함께 동작해요 (entity_id 만 본인 환경에 맞게 지정하세요).  
*All three blueprints use the standard `climate.set_preset_mode` service, so they also work alongside any other HA-thermostat integration — just point them at the right entity_ids.*

원본 YAML: [blueprints/automation/bestin/](https://github.com/dlxmax/ha-bestin-fork/tree/main/blueprints/automation/bestin)  
*Raw YAML files: [blueprints/automation/bestin/](https://github.com/dlxmax/ha-bestin-fork/tree/main/blueprints/automation/bestin)*

### 객실 온도 센서 / Room temperature sensors (v1.4.16)

앱을 통해 받는 월패드 온도는 정수로 내려서 와요 (월패드 화면은 0.5 단위, RS-485 경로는 해당 없어요). 월패드 센서는 실제보다 높게 읽을 때도 많아요. 통합 옵션에서 방마다 HA 온도 센서를 고를 수 있어요 (선택).  
*Through the app the wallpad temperature arrives as whole degrees, rounded down (the wall unit itself shows halves; RS-485 is not affected), and the wall unit often reads high. In the integration options you can pick an HA temperature sensor for each room (optional).*

- 온도조절기의 현재 온도가 그 센서 값으로 바뀌고, 듀티 사이클 프리셋도 그 값으로 제어해요. 센서 값은 바뀌는 즉시 반영되고 단지 서버 요청은 늘지 않아요.  
  *The thermostat's current temperature shows that sensor, and duty-cycle presets control on it. Changes apply as they happen, with no extra requests to the complex server.*
- 월패드 값은 `wallpad_temperature` 속성에 남아요. ON 펄스의 setpoint 는 계속 월패드 값을 기준으로 계산해요 (월패드는 자기 센서로 판단하니까요).  
  *The wallpad's reading stays available as the `wallpad_temperature` attribute. ON pulses are still computed from it, because the wallpad decides with its own sensor.*
- 센서가 unavailable 이 되면 그 방은 월패드 온도로 돌아가요. 'none' 프리셋에서는 월패드가 자기 센서로 판단하니까 표시만 바뀌어요.  
  *If the sensor goes unavailable the room falls back to the wallpad reading. On the 'none' preset the wallpad still decides with its own sensor, so only the display changes.*

### 알고리즘 / Algorithm (참고 / reference)

iparkapp 게이트웨이에서 활성 프리셋이 슬로우 듀티 사이클을 트리거할 때:

```
temp = 매핑된 객실 센서 값, 없으면 월패드 값 / mapped room sensor, else the wallpad reading
temp_error = user_setpoint - temp
duty% = clamp(0, 100, (temp_error / proportional_band) × 100)
ON 시간 = cycle × duty% (사이클 시작부터) / ON for cycle × duty% from the start of each cycle
```

추가 제약 / additional constraint: 프리셋별 최소 on / off 시간. 수치는 `duty_cycle.py` 의 `PRESET_PROFILES` 를 보세요.  
*Plus per-preset minimum on/off times. See `PRESET_PROFILES` in `duty_cycle.py` for the numbers.*

참고 문헌 (직접 확인한 것만) / References (checked): 짧은 고정 펄스 + 가변 휴지 / short fixed pulse with variable off-time (펄스는 배관 물이 한 번 바뀌는 시간 이하, 보통 4분 / pulse no longer than one loop flush, typically 4 min): Tang et al., *Building and Environment* 127 (2018), doi:10.1016/j.buildenv.2017.11.004, [전문 / full text](https://escholarship.org/uc/item/31s4x6jr). 배관 속 정체수 냉각과 공급·환수 온도 기반 제어 / standing-water cooling and supply/return based control: Danfoss US 9027847 B2, US 6533186 B2. 온돌 바닥 승온·냉각 시간 / ondol floor warm-up and cool-down times: 이태강 외 2013, doi:10.12813/kieae.2013.13.3.061.  
*Only sources that were actually opened are listed.*

순수 비례 제어라 방 온도는 setpoint 보다 약간 아래에서 안정되는 편이에요. 프리셋 수치는 검증되지 않은 연구 파일에서 왔고, 실측으로 조정하지 않았어요.  
*Proportional-only control tends to settle slightly below the setpoint. The preset numbers came from the unverified research file and have not been tuned against measurements.*

### 알려진 제한 / Known caveats

- **월패드 setpoint 를 잠깐 바꿔요 (듀티 사이클이 켜진 방만).** ON 펄스 동안 월패드 화면에는 사용자 값보다 높은 setpoint 가 잠시 보여요. 월패드의 내장 임계값을 넘기려고 그래요. HA UI 는 항상 사용자가 정한 실제 값을 보여 줘요.  
  *Wallpad setpoint is momentarily manipulated on duty-cycle-active rooms — during the ON pulse the wallpad face shows a setpoint elevated above your true target (forces the wallpad's onboard threshold to call for heat). HA always displays your real value.*
- **HA 를 다시 시작해도 v1.4.11 부터 자동으로 복원돼요.** 컨트롤러 상태는 여전히 메모리에만 있지만, 온도조절기 엔티티가 HA 표준 `RestoreEntity` 로 마지막 프리셋과 setpoint 를 되살려요 (HA 는 최대 7일간 보관해서 짧은 정전도 괜찮아요). 복원 후 첫 tick (≤30 s) 에서 최소 on/off 시간을 기다리지 않고 바로 다시 판단해요. 재시작 중 월패드가 어떤 상태였는지 알 수 없어서, 관측된 온도로 처음부터 다시 계산해요. v1.4.10 까지는 재시작할 때마다 모든 방이 조용히 'none' 으로 떨어졌어요.  
  *HA restart — automatically restored since v1.4.11. The controller state still lives in memory, but the thermostat entities recover their last preset and setpoint through HA's standard `RestoreEntity` (HA keeps these for up to 7 days, so brief outages survive too). The first tick after a restore re-evaluates immediately rather than waiting out a min-on/min-off window: we cannot know what the wallpad did while HA was down, so the decision is recomputed from an observed temperature. Through v1.4.10 every restart silently dropped every room to 'none'.*
- **종료할 때 월패드에 제어권을 돌려줘요 (v1.4.11).** ON 펄스 중에 컨트롤러가 멈추면 월패드는 현재온도+5 °C 라는 부풀린 setpoint 를 계속 물고 있게 돼요. 그래서 종료 / 언로드 직전에 사용자의 실제 setpoint 를 `on/<setpoint>` 로 보내 월패드 자체 로직으로 돌려놔요 (OFF 가 아니라 ON 이에요. 한겨울에 난방을 꺼 버리는 것보다 안전해요). 서버가 응답하지 않아도 10 초 안에 포기해서 HA 종료가 막히지 않아요.  
  *Hands control back to the wallpad on shutdown (v1.4.11). If the controller stops mid-ON-pulse, the wallpad is left holding an inflated current+5 °C setpoint with nobody to walk it back. Before stopping, the integration sends the user's real setpoint as `on/<setpoint>` so the wallpad's onboard thermostat takes over — ON rather than OFF, because unsmoothed heating at the right temperature beats a cold floor in a Korean winter. Capped at 10 s so an unresponsive server can't block HA shutdown.*
- **다른 가족이 월패드를 직접 조작하면**, 다음 폴링에서 그 값이 듀티 사이클 컨트롤러가 받아들여요. 원하던 값이 아니면 HA 에서 다시 설정하세요.  
  *If someone changes the setpoint at the wallpad directly, the next poll adopts it. Re-set in HA if not desired.*
- **밸브가 더 자주 움직여요.** 듀티 사이클은 분배기 구동기를 사이클마다 열고 닫아요. 수명에 미치는 영향은 측정된 자료가 없어요 (이전 버전의 "5-8년" 수치는 근거가 없었어요). 기본값 (None) 은 듀티 사이클을 쓰지 않아요.  
  *More valve operations. Duty cycling opens and closes the manifold actuators every cycle. There is no measured data on what that does to their life (the "5-8 years" figure in earlier versions had no basis). The default (None) does not duty cycle.*

## 문제 신고 / Reporting a problem

1. **설정 > 기기 및 서비스 > BESTIN > ⚙ (톱니바퀴) > 문제 신고** 를 고르고, 무엇이 안 되는지 적으세요 (비워 둬도 돼요).  
   *Settings > Devices & services > BESTIN > ⚙ (gear icon) > Report a problem, and describe what is not working (optional).*
2. 다음 화면에서 **진단 파일 내려받기** 를 누른 뒤 **GitHub 이슈 열기** 를 여세요. 버전, 연결 방식, 장치별 마지막 응답, 최근 오류가 미리 채워져 있어요.  
   *On the next screen, click **Download the diagnostics file**, then **Open the GitHub issue**. The version, connection type, last reply per device and recent errors are filled in.*
3. 내려받은 파일을 이슈에 끌어다 놓고, 내용을 확인한 뒤 제출해 주세요. 내려받기 링크가 안 되면 **BESTIN > ⋮ (점 세 개) > 진단 다운로드** 로 받을 수 있어요.  
   *Drag the downloaded file into the issue, review it, then submit. If the download link fails, use **BESTIN > ⋮ (three dots) > Download diagnostics**.*

비밀번호, 아이디, IP, 좌표, 세션, 동·호수는 가려져요. 단지 코드와 이름은 단지별 서버 차이를 구분하려고 남겨요. BESTIN 은 아무것도 자동으로 보내지 않아요.  
*Passwords, IDs, IPs, coordinates, sessions and your unit number are hidden. The complex code and name stay, to tell one complex's server from another. BESTIN never sends anything by itself.*

설정 단계에서 오류가 나면 양식에 실제 오류와 신고 링크가 함께 표시돼요.  
*If setup itself fails, the form shows the actual error with a report link.*

<details>
<summary>디버그 로그를 요청받았을 때 / If you are asked for a debug log</summary>

`configuration.yaml` 에 아래를 추가하고 HA 를 다시 시작한 뒤, 문제를 다시 일으키고 로그를 이슈에 붙여 주세요.  
*Add this to `configuration.yaml`, restart HA, reproduce the problem and paste the log into the issue.*

```yaml
logger:
  default: info
  logs:
    custom_components.bestin: debug
```

</details>
