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
| 지역난방 공급 온도 / District heating supply temp | `unit_cnt` 를 초과한 추가 'room' 은 `heatsource` 센서로 노출 (예: 지역난방 공급 온도)<br>*Any 'room' beyond `unit_cnt` is exposed as a read-only `heatsource` sensor.* |
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

## 디버깅 / Debugging

문제가 있는 경우 `configuration.yaml` 에 아래 내용을 추가하고 HA 를 재시작하면 상세 로그를 얻을 수 있습니다.  
*If something doesn't work, add the snippet below to `configuration.yaml` and restart HA to get verbose logs.*

```yaml
logger:
  default: info
  logs:
    custom_components.bestin: debug
```
