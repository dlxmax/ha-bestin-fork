[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# BESTIN

> 한국 BESTIN / 현대 IPARK 월패드용 Home Assistant 커스텀 컴포넌트.  
> *Home Assistant custom component for Korean BESTIN / Hyundai IPARK wallpads.*

이 저장소는 [원본 `lunDreame/ha-bestin`](https://github.com/lunDreame/ha-bestin) 을 포크하여, 같은 단지에서도 동작하지 않던 기존 두 가지 방식을 보완하는 세 번째 옵션인 **iPark 스마트홈 앱** 을 추가해요. 자세한 프로젝트 소개는 [ABOUT.md](./ABOUT.md) 를 보세요.  
*This repo forks [the upstream `lunDreame/ha-bestin`](https://github.com/lunDreame/ha-bestin) and adds a third gateway, **iPark Smarthome App**, that fills the gap when the two existing methods don't work in a given complex. See [ABOUT.md](./ABOUT.md) for the full project overview.*

## 목차 / Contents

- [프로젝트 소개 / About](#프로젝트-소개--about)
- [유지보수 현황 / Maintenance status](#유지보수-현황--maintenance-status)
- [어떤 방식을 선택해야 하나요? / Which method should I pick?](#어떤-방식을-선택해야-하나요--which-method-should-i-pick)
- [추가 배경 / Why this fork exists](#추가-배경--why-this-fork-exists)
- [설치 / Installation](#설치--installation)
- [준비 / Prerequisites (RS-485 only)](#준비--prerequisites-rs-485-only)
- [기능 / Features](#기능--features)
- [문제 신고 / Reporting a problem](#문제-신고--reporting-a-problem)
- [기여 / Contributing](#기여--contributing)

## 프로젝트 소개 / About

세 가지 연결 방식 중 본인 단지·환경에 맞는 것을 선택해 월패드를 Home Assistant 에 연동해요. 통합과 모든 문서는 한국어와 영어를 함께 지원해요.  
*Three connection methods, pick whichever matches your complex/setup. Integration and all docs are bilingual (Korean first, English second).*

## 유지보수 현황 / Maintenance status

원본 [`lunDreame/ha-bestin`](https://github.com/lunDreame/ha-bestin) 의 작업이 v1.1.9 이후로 중단되어, 이 포크 [`dlxmax/ha-bestin-fork`](https://github.com/dlxmax/ha-bestin-fork) 가 유지보수를 이어 받았어요. 버전별 변경 내용은 [Releases](https://github.com/dlxmax/ha-bestin-fork/releases) 에서 볼 수 있어요.  
*Upstream [`lunDreame/ha-bestin`](https://github.com/lunDreame/ha-bestin) development stopped after v1.1.9. This fork [`dlxmax/ha-bestin-fork`](https://github.com/dlxmax/ha-bestin-fork) has taken over maintenance. See [Releases](https://github.com/dlxmax/ha-bestin-fork/releases) for what changed in each version.*

## 어떤 방식을 선택해야 하나요? / Which method should I pick?

| 방식 / Method | 적합한 환경 / Best for | 가이드 / Guide |
|---|---|---|
| **로컬 RS-485 / Local RS-485** | 월패드 라인에 직접 연결할 하드웨어가 있고, 인터넷·서버에 기대지 않는 구성을 원할 때.<br>*You have RS-485 hardware and prefer a server-free setup.* | [guide/install.md](./guide/install.md) |
| **IPARK 스마트홈 클라우드 / IPARK Smart Home cloud** | 공식 클라우드 (`center.hdc-smart.com`) 가 잘 동작하는 신축·중형 단지.<br>*Newer complexes where the official cloud responds.* | [guide/center.md](./guide/center.md) |
| **iPark 스마트홈 앱 / iPark Smarthome App** | 안드로이드 iPark 스마트홈 앱은 동작하나 RS-485 어댑터 / 클라우드 / 단지 웹사이트가 동작하지 않는 구형 단지.<br>*Older complexes where the Android iPark Smarthome app works but RS-485, cloud, or the apartment website don't.* | [guide/iparkapp.md](./guide/iparkapp.md) |

잘 모르겠으면 **iPark 스마트홈 앱 옵션** 부터 써 보세요. 하드웨어도 토큰 등록도 필요 없어서 가장 쉬워요.  
*If unsure, try the **iPark Smarthome App** option first: no hardware, no token registration, lowest barrier to entry.*

## 추가 배경 / Why this fork exists

기존 두 가지 방식 (RS-485 / 웹사이트 기반 클라우드 연동) 은 이 포크 작성자의 집에서 동작하지 않았어요. 월패드는 RS-485 보다 오래된 RS-422 라인을 사용해 어댑터로 신호 해석이 어려웠고, 단지 웹사이트(`http://<단지IP>/`) 의 제어는 응답이 없었어요. 반면 안드로이드 [iPark 스마트홈 앱](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet) 은 같은 단지 서버에서 잘 동작했어요. 앱을 리버스 엔지니어링한 결과, 앱은 웹사이트와 동일한 URL 을 호출하지만 두 가지 핵심 차이가 있었어요. 정확한 PHP 경로 (`/webapp/data/...`) 와 필수 AJAX 헤더 (`X-Requested-With: XMLHttpRequest`) 예요. 'iPark 스마트홈 앱' 옵션은 이 두 차이를 그대로 반영해서 같은 단지에서 안정적으로 동작해요.  
*The two existing methods (RS-485 and the website-based cloud integration) didn't work in this fork's author's home. The wallpad uses the older RS-422 line so off-the-shelf adapters can't read it cleanly, and **the apartment website's controls (`http://<complex-IP>/`) silently dropped every command**. The Android [iPark Smarthome app](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet) however works fine against the same server. Reverse-engineering the app revealed it hits the same server but with two critical differences from the website: the correct PHP path (`/webapp/data/...`) and a mandatory AJAX header (`X-Requested-With: XMLHttpRequest`). The new "iPark Smarthome App" option mirrors both, which makes it work reliably in homes where the website method does not.*

## 설치 / Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dlxmax&repository=ha-bestin-fork&category=Integration)

이 통합을 설치하려면 이 GitHub Repo 를 HACS Custom Repositories 에 추가하거나 위의 배지를 클릭하세요. 설치한 뒤 Home Assistant 를 다시 시작하세요.  
*Add this GitHub repo to HACS Custom Repositories or click the badge above. Restart Home Assistant after install.*

1. **기기 및 서비스** 메뉴에서 **통합구성요소 추가하기** 를 클릭하세요.  
   *In the **Devices & Services** menu, click **Add Integration**.*
2. **브랜드 이름 검색** 탭에 `BESTIN` 을 입력하고 검색 결과에서 클릭하세요.  
   *Search for `BESTIN` and pick it from the results.*
3. 아래 세 옵션 중 본인 환경에 맞는 것을 고르세요 / *Then pick the option that matches your setup:*

   #### 1. 로컬 통신 / Local communication (RS-485)
   - **IP 주소 / IP address**:
     - **EW11** 사용 시: `192.168.x.x` 형식의 IP 주소를 입력하세요 / *EW11: enter an IP such as `192.168.x.x`*
     - **USB to 485** 사용 시: `/dev/ttyXXX` 경로를 입력하세요 / *USB-to-485: enter a `/dev/ttyXXX` path*
   - **포트 / Port**: EW11 의 포트 번호 (기본값 8899). USB-to-485 는 비워 두세요. / *EW11 port (default 8899). Leave empty for USB-to-485.*
   - 어댑터 설치는 [guide/install.md](./guide/install.md) 를 보세요. / *See [install guide](./guide/install.md) for adapter setup.*

   #### 2. IPARK 스마트홈 클라우드 / IPARK Smart Home cloud
   - 버전 (1.0 / 2.0) 을 고른 뒤 단지 IP / UUID 등록 절차를 진행하세요. / *Pick the version (1.0 / 2.0) and complete the IP / UUID registration steps.*
   - 자세한 절차는 [guide/center.md](./guide/center.md) 를 보세요. / *Full instructions in [guide/center.md](./guide/center.md).*

   #### 3. iPark 스마트홈 앱 / iPark Smarthome App
   - 자동 조회된 단지 목록에서 자신의 단지를 고르고, 안드로이드 앱과 같은 아이디·비밀번호로 로그인하세요. IP 나 토큰은 입력할 필요 없어요. / *Pick your complex from the auto-fetched directory, then sign in with the same credentials you use in the Android app. No IP entry, no token copy-paste.*
   - 자세한 내용은 [guide/iparkapp.md](./guide/iparkapp.md) 를 보세요. / *See [guide/iparkapp.md](./guide/iparkapp.md) for details.*

4. 설정을 마치고 통합이 로드되면 기기가 자동으로 나타나요.  
   *Once the integration finishes loading, the new devices will appear automatically.*

## 준비 / Prerequisites (RS-485 only)

iPark 스마트홈 앱 / 클라우드 옵션은 따로 하드웨어가 필요 없어요. 아래 항목은 **로컬 RS-485** 옵션에만 해당해요.  
*The iPark Smarthome App and cloud options need no extra hardware. The list below applies only to the **local RS-485** option.*

- EW11 또는 USB-to-485 컨버터 2개 (게이트웨이 없는 일체형 세대는 1 개면 돼요). / *2× EW11 or USB-to-485 converters (1× is enough for gateway-less units).*
- 라인을 확보하고 게이트웨이 타입을 확인하세요 (게이트웨이가 있는 세대인지, 월패드 뒤쪽 라인에 직접 꽂는지). / *Confirm wiring and gateway type (with-gateway vs. plug into the line behind the wallpad).*
- 어댑터 설치는 [guide/install.md](./guide/install.md) 를 보세요. / *Adapter setup in [install guide](./guide/install.md).*
  - 연결이 잘 됐는지는 시리얼 포트 모니터로 확인하세요. BESTIN 월패드의 프레임은 `02` 로 시작해요. [예시](./guide/packet_dump.txt). / *Verify the link with a serial port monitor. BESTIN frames start with `02`. See [sample data](./guide/packet_dump.txt).*
  - 디밍 세대는 [디밍 예시](./guide/dimming_packet_dump.txt) 를 보세요. / *For dimming-light households, see the [dimming sample](./guide/dimming_packet_dump.txt).*

## 기능 / Features

![추가된 기기](./images/added_devices.png)

| 기기 / Device | 지원 / Supported | 비고 / Notes |
|---|---|---|
| 콘센트 / Outlet | O | 실시간 사용량, 대기전력 자동차단 / Live usage, standby auto-cutoff |
| 조명 / Light | O | 디밍, 색온도 / Dimming, color temperature |
| 엘리베이터 / Elevator | O | 클라우드 v2.0 한정 / Cloud v2.0 only |
| HEMS | O | 실시간 + 총합 사용량 / Live + total usage |
| 환기 / Ventilation | O | 프리셋 (자연풍) / Presets (natural ventilation) |
| 가스 / Gas valve | O | 닫기 전용 (앱 동일) / Close-only (matches the app) |
| 도어락 / Door lock | O | RS-485 · 클라우드: 스위치, 켜기와 끄기가 같은 RS-485 패킷을 보내고, 클라우드 v1 은 명령을 지원하지 않아요. iPark 스마트홈 앱: 상태 표시만 (앱 동일) / RS-485 and cloud: switch; on and off send the same RS-485 packet, and cloud v1 does not support the command. iPark Smarthome App: status only (matches the app) |
| 난방 / Heating | O | 객실 + 추가 비제어 난방 온도 센서 (있는 경우, 정확한 의미는 단지마다 상이). 설정 단위 0.5°, iPark 스마트홈 앱 옵션은 1° (단지 서버가 정수만 받아요). 로컬 RS-485 는 난방 중 / 대기 상태도 보여 줘요. / Per-room + an extra uncontrollable heat-temperature sensor where the wallpad reports more 'rooms' than it has thermostats (exact meaning varies by complex). Setpoints in 0.5° steps, 1° on the iPark Smarthome App option (the complex server only takes whole degrees). Local RS-485 also shows heating or idle. |
| 객실별 실내 온도 센서 / Per-room temperature sensors | O | iPark 스마트홈 앱 옵션 한정. 통합 옵션에서 객실마다 HA 온도 센서를 지정하면 표시 온도와 듀티 사이클 제어가 월패드 대신 그 센서를 써요 (앱 경로는 월패드 온도를 정수로 내려요). / iPark Smarthome App option only. Pick an HA temperature sensor per room in the integration options and the displayed temperature and duty-cycle control use it instead of the wallpad (the app path floors wallpad readings to whole degrees). |
| 외출 모드 / Away mode | O | iPark 스마트홈 앱 옵션 한정 (별도 entity) / iPark Smarthome App option only (separate entity) |
| 에너지 모니터링 / Energy monitoring | O | 전기 / 가스 / 난방 / 온수 / 수도, iPark 스마트홈 앱 옵션 한정. 매시 10분에 갱신, 소수 첫째 자리 표시, 검침값이 없으면 0 대신 '-'. 누적 사용량은 HA 에너지 대시보드에 추가할 수 있어요. / Electric / Gas / Heat / Hot water / Water, iPark Smarthome App option only. Refreshed 10 minutes past each hour, shown to one decimal, a dash instead of a false 0 when no reading is published. Cumulative totals can be added to the HA Energy dashboard. |
| 표준 HA 프리셋 (난방) / Standard HA presets (heating) | O | Comfort / Eco / Sleep / Away / Vacation / Frost / Boost, 객실별 / per-room. iPark 스마트홈 앱 옵션에서는 슬로우 듀티 사이클 (시간 비례 제어) 이 함께 적용돼요 (다른 게이트웨이는 setpoint 만 바꿔요). / On the iPark Smarthome App option these also engage a software slow duty cycle (time-proportional control); on other gateways they just change the setpoint. |
| RS-485 연결 복구 / RS-485 connection recovery | O | 연결이 끊기면 다시 연결하고, 어긋난 데이터 뒤에는 다음 패킷을 다시 찾아요. / Reconnects after a drop, and finds the next packet after bad data. |
| HA 자동화 Blueprints | O | 야간 setback / 휴가 일정 / 외출 자동 감지. `blueprints/automation/bestin/` 의 3 개 YAML 을 한 번 임포트하면 HA UI 에서 객실·시각·도우미를 채워 쓸 수 있어요. / Three importable blueprints (night setback, vacation window, away-when-empty) under `blueprints/automation/bestin/`. |
| 단지 서버 부하 감소·장애 대응 / Server load and outages | O | iPark 스마트홈 앱 옵션 한정. 난방은 방마다 켜진 방은 5분, 꺼진 방은 30분, 그 외 장치는 60초마다 조회하고, 세대에 없는 장치는 조회 빈도를 줄여요. 서버 장애 때는 5분마다 다시 시도하고 HA 알림을 띄워요. / iPark Smarthome App option only. Thermostats are polled room by room, every 5 min for a room that is on and every 30 min for one that is off, other devices every 60 s, and devices the home doesn't have are backed off. During a server outage it retries every 5 min and raises an HA notification. |

- 추가 기기·속성이 필요하면 [이슈](https://github.com/dlxmax/ha-bestin-fork/issues) 를 등록해 주세요. / *Open an [issue](https://github.com/dlxmax/ha-bestin-fork/issues) if your household has devices not in the table above.*

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

## 기여 / Contributing

- 월패드 버전 3.0 과 시리얼 (USB-to-485) 통신은 아직 시험해 보지 않았어요. / *Wallpad 3.0 and serial (USB-to-485) communication are not tested yet.*
- 로컬 RS-485 수정 중 일부는 다른 포크에서 가져온 것이라 ([ABOUT.md](./ABOUT.md#감사의-말--acknowledgments) 참고), 이 포크 작성자의 월패드 (RS-422) 에서는 시험할 수 없어요. RS-485 를 쓰시는 분들이 결과를 알려 주시면 정말 도움이 돼요. / *Some local RS-485 fixes come from other forks (see [ABOUT.md](./ABOUT.md#감사의-말--acknowledgments)) and can't be tested on this fork author's RS-422 wallpad. Reports from RS-485 users are welcome.*
- **[Pull request](https://github.com/dlxmax/ha-bestin-fork/pulls) 환영해요.** 버그 수정, 새 기기, 다른 단지에서 시험한 결과 모두 좋아요. / ***[Pull requests](https://github.com/dlxmax/ha-bestin-fork/pulls) welcome.** Bug fixes, new devices and test results from other complexes are all useful.*
- Pull request 를 보내면, 그 변경을 이 프로젝트에 넣어 배포하는 데 동의한 것으로 봐요. / *By opening a pull request, you agree that your change may be included and distributed in this project.*
- 이 통합을 쓰다가 생긴 문제는 책임지지 않아요. / *Use at your own risk; no warranty is provided.*
