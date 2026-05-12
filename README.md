[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# BESTIN

> 한국 BESTIN / 현대 IPARK 월패드용 Home Assistant 커스텀 컴포넌트.  
> *Home Assistant custom component for Korean BESTIN / Hyundai IPARK wallpads.*

본 저장소는 [원본 `lunDreame/ha-bestin`](https://github.com/lunDreame/ha-bestin) 을 포크하여, 같은 단지에서도 동작하지 않던 기존 두 가지 방식을 보완하는 세 번째 옵션 — **iPark 스마트홈 앱** — 을 추가합니다. 자세한 프로젝트 소개는 [ABOUT.md](./ABOUT.md) 참조.  
*This repo forks [the upstream `lunDreame/ha-bestin`](https://github.com/lunDreame/ha-bestin) and adds a third gateway — **iPark Smarthome App** — that fills the gap when the two existing methods don't work in a given complex. See [ABOUT.md](./ABOUT.md) for the full project overview.*

## 목차 / Contents

- [프로젝트 소개 / About](#프로젝트-소개--about)
- [유지보수 현황 / Maintenance status](#유지보수-현황--maintenance-status)
- [어떤 방식을 선택해야 하나요? / Which method should I pick?](#어떤-방식을-선택해야-하나요--which-method-should-i-pick)
- [추가 배경 / Why this fork exists](#추가-배경--why-this-fork-exists)
- [설치 / Installation](#설치--installation)
- [준비 / Prerequisites (RS-485 only)](#준비--prerequisites-rs-485-only)
- [기능 / Features](#기능--features)
- [기여 / Contributing](#기여--contributing)
- [디버깅 / Debugging](#디버깅--debugging)

## 프로젝트 소개 / About

세 가지 연결 방식 중 본인 단지·환경에 맞는 것을 선택해 월패드를 Home Assistant 에 연동합니다. 통합과 모든 문서는 한국어 / 영어를 동시 지원하며, 기존 코드 경로는 그대로 유지된 채 새 옵션이 **추가**된 것이므로 기존 사용자에게 영향이 없습니다.  
*Three connection methods, pick whichever matches your complex/setup. Integration and all docs are bilingual (Korean first, English second). The new option is **additive** — no existing code path was modified, so prior users see no behavioural change.*

## 유지보수 현황 / Maintenance status

원본 [`lunDreame/ha-bestin`](https://github.com/lunDreame/ha-bestin) 의 작업이 v1.1.9 이후로 중단되어, 본 포크 [`dlxmax/ha-bestin-fork`](https://github.com/dlxmax/ha-bestin-fork) 가 유지보수를 이어 받았습니다. 본 포크의 직전 릴리스 v1.2.0 은 lunDreame v1.1.9 에서 발견된 버그를 정리한 버전입니다 (Python 3.14 호환, 게이트웨이 모드 감지 타임아웃, 무한 리로드 루프, 0x31 패킷 변형, 온도조절기 파싱 가드 등). 본 **v1.3.0** 에서는 신규 'iPark 스마트홈 앱' 옵션이 추가되었습니다.  
*Upstream [`lunDreame/ha-bestin`](https://github.com/lunDreame/ha-bestin) development stopped after v1.1.9. This fork [`dlxmax/ha-bestin-fork`](https://github.com/dlxmax/ha-bestin-fork) has taken over maintenance. Our previous release **v1.2.0** carried bug fixes against lunDreame's v1.1.9 (Python 3.14 compatibility, gateway-mode detection timeout, infinite reload loop, 0x31 packet variants, thermostat parsing guard, etc.). The new **v1.3.0** adds the "iPark Smarthome App" option.*

## 어떤 방식을 선택해야 하나요? / Which method should I pick?

| 방식 / Method | 적합한 환경 / Best for | 가이드 / Guide |
|---|---|---|
| **로컬 RS-485 / Local RS-485** | 월패드 라인에 직접 연결할 하드웨어가 있고, 인터넷·서버 의존이 없는 구성을 선호.<br>*You have RS-485 hardware and prefer a server-free setup.* | [guide/install.md](./guide/install.md) |
| **IPARK 스마트홈 클라우드 / IPARK Smart Home cloud** | 신축·중형 단지로 공식 클라우드 (`center.hdc-smart.com`) 가 정상 동작.<br>*Newer complexes where the official cloud responds.* | [guide/center.md](./guide/center.md) |
| **iPark 스마트홈 앱 / iPark Smarthome App** _(신규 / new)_ | 안드로이드 iPark 스마트홈 앱은 동작하나 RS-485 어댑터 / 클라우드 / 단지 웹사이트가 동작하지 않는 구형 단지.<br>*Older complexes where the Android iPark Smarthome app works but RS-485, cloud, or the apartment website don't.* | [guide/iparkapp.md](./guide/iparkapp.md) |

선택이 어려우시면 **iPark 스마트홈 앱 옵션** 부터 시도해 보세요. 별도 하드웨어 / 토큰 등록이 필요 없어 가장 진입 장벽이 낮습니다.  
*If unsure, try the **iPark Smarthome App** option first — no hardware, no token registration, lowest barrier to entry.*

## 추가 배경 / Why this fork exists

기존 두 가지 방식 (RS-485 / 웹사이트 기반 클라우드 연동) 은 본 포크 작성자의 가정에서 동작하지 않았습니다. 월패드는 RS-485 보다 오래된 RS-422 라인을 사용해 어댑터로 신호 해석이 어려웠고, 단지 웹사이트(`http://<단지IP>/`) 의 제어는 응답이 없었습니다. 반면 안드로이드 [iPark 스마트홈 앱](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet) 은 같은 단지 서버에서 정상 동작했습니다. 앱을 리버스 엔지니어링한 결과, 앱은 웹사이트와 동일한 URL 을 호출하지만 두 가지 핵심 차이가 있었습니다 — 정확한 PHP 경로 (`/webapp/data/...`) 와 필수 AJAX 헤더 (`X-Requested-With: XMLHttpRequest`). 본 'iPark 스마트홈 앱' 옵션은 이 두 가지 차이를 정확히 반영해 동일 단지 환경에서 안정적으로 동작합니다.  
*The two existing methods (RS-485 and the website-based cloud integration) didn't work in this fork's author's home — the wallpad uses the older RS-422 line so off-the-shelf adapters can't read it cleanly, and **the apartment website's controls (`http://<complex-IP>/`) silently dropped every command**. The Android [iPark Smarthome app](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet) however works fine against the same server. Reverse-engineering the app revealed it hits the same server but with two critical differences from the website: the correct PHP path (`/webapp/data/...`) and a mandatory AJAX header (`X-Requested-With: XMLHttpRequest`). The new "iPark Smarthome App" option mirrors both, which makes it work reliably in homes where the website method does not.*

## 설치 / Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dlxmax&repository=ha-bestin-fork&category=Integration)

이 통합을 설치하려면 이 GitHub Repo 를 HACS Custom Repositories 에 추가하거나 위의 배지를 클릭하세요. 설치 후 Home Assistant 를 재부팅하세요.  
*Add this GitHub repo to HACS Custom Repositories or click the badge above. Restart Home Assistant after install.*

1. **기기 및 서비스** 메뉴에서 **통합구성요소 추가하기** 를 클릭합니다.  
   *In the **Devices & Services** menu, click **Add Integration**.*
2. **브랜드 이름 검색** 탭에 `BESTIN` 을 입력하고 검색 결과에서 클릭합니다.  
   *Search for `BESTIN` and pick it from the results.*
3. 아래 세 옵션 중 본인 환경에 맞는 것을 선택합니다 / *Then pick the option that matches your setup:*

   #### 1. 로컬 통신 / Local communication (RS-485)
   - **IP 주소 / IP address**:
     - **EW11** 사용 시: `192.168.x.x` 형식의 IP 주소 입력 / *EW11: enter an IP such as `192.168.x.x`*
     - **USB to 485** 사용 시: `/dev/ttyXXX` 경로 입력 / *USB-to-485: enter a `/dev/ttyXXX` path*
   - **포트 / Port**: EW11 의 포트 번호 (기본값 8899). USB-to-485 사용 시 생략. / *EW11 port (default 8899). Leave empty for USB-to-485.*
   - 자세한 어댑터 설치는 [guide/install.md](./guide/install.md) 참조. / *See [install guide](./guide/install.md) for adapter setup.*

   #### 2. IPARK 스마트홈 클라우드 / IPARK Smart Home cloud
   - 버전 (1.0 / 2.0) 선택 후 단지 IP / UUID 등록 절차를 진행합니다. / *Pick the version (1.0 / 2.0) and complete the IP / UUID registration steps.*
   - 자세한 절차는 [guide/center.md](./guide/center.md) 참조. / *Full instructions in [guide/center.md](./guide/center.md).*

   #### 3. iPark 스마트홈 앱 / iPark Smarthome App _(신규 / new)_
   - 자동 조회된 단지 목록에서 자신의 단지를 선택하고, 안드로이드 앱과 동일한 아이디·비밀번호로 로그인합니다. IP·토큰 입력이 필요 없습니다. / *Pick your complex from the auto-fetched directory, then sign in with the same credentials you use in the Android app — no IP entry, no token copy-paste.*
   - 자세한 내용은 [guide/iparkapp.md](./guide/iparkapp.md) 참조. / *See [guide/iparkapp.md](./guide/iparkapp.md) for details.*

4. 설정이 완료된 후, 컴포넌트가 로드되면 생성된 기기를 사용하실 수 있습니다.  
   *Once the integration finishes loading, the new devices will appear automatically.*

## 준비 / Prerequisites (RS-485 only)

iPark 스마트홈 앱 / 클라우드 옵션은 별도의 하드웨어가 필요 없습니다. 아래 항목은 **로컬 RS-485** 옵션 한정입니다.  
*The iPark Smarthome App and cloud options need no extra hardware. The list below applies only to the **local RS-485** option.*

- EW11 또는 USB-to-485 컨버터 2개 (게이트웨이 없는 일체형 세대는 1 개로 가능). / *2× EW11 or USB-to-485 converters (1× is enough for gateway-less units).*
- 라인 확보 및 게이트웨이 타입 구분 (게이트웨이 있는 세대인지, 월패드 뒤쪽 라인에 직접 꼽는지 확인). / *Confirm wiring and gateway type (with-gateway vs. plug into the line behind the wallpad).*
- 어댑터 설치는 [guide/install.md](./guide/install.md) 참조. / *Adapter setup in [install guide](./guide/install.md).*
  - 정상 연결 확인 시 시리얼 포트몬을 사용하세요. BESTIN 월패드의 프레임은 `02` 로 시작합니다. [예시](./guide/packet_dump.txt). / *Verify the link with a serial port monitor — BESTIN frames start with `02`. See [sample data](./guide/packet_dump.txt).*
  - 디밍 세대는 [디밍 예시](./guide/dimming_packet_dump.txt) 참조. / *For dimming-light households, see the [dimming sample](./guide/dimming_packet_dump.txt).*

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
| 도어락 / Door lock | O | 상태 표시만 (앱 동일) / Status only (matches the app) |
| 난방 / Heating | O | 객실 + 추가 비제어 난방 온도 센서 (있는 경우, 정확한 의미는 단지마다 상이) / Per-room + an extra uncontrollable heat-temperature sensor where the wallpad reports more 'rooms' than it has thermostats (exact meaning varies by complex) |
| 외출 모드 / Away mode | O | iPark 스마트홈 앱 옵션 한정 (별도 entity) / iPark Smarthome App option only (separate entity) |
| 에너지 모니터링 / Energy monitoring | O | 전기 / 가스 / 난방 / 온수 / 수도 — iPark 스마트홈 앱 옵션 한정 / Electric / Gas / Heat / Hot water / Water — iPark Smarthome App option only |
| 표준 HA 프리셋 (난방) / Standard HA presets (heating) | O | Comfort / Eco / Sleep / Away / Vacation / Frost / Boost — 객실별 / per-room. iPark 스마트홈 앱 옵션에서는 슬로우 듀티 사이클 (시간 비례 제어) 이 함께 적용됩니다 (다른 게이트웨이는 setpoint 만 변경). v1.4.0+. / On the iPark Smarthome App option these also engage a software slow duty cycle (time-proportional control); on other gateways they just change the setpoint. v1.4.0+. |
| HA 자동화 Blueprints | O | 야간 setback / 휴가 일정 / 외출 자동 감지 — `blueprints/automation/bestin/` 의 3 개 YAML 을 한 번 임포트하면 HA UI 에서 객실·시각·도우미를 채워 사용. v1.4.2+. / Three importable blueprints (night setback, vacation window, away-when-empty) under `blueprints/automation/bestin/`. v1.4.2+. |

> **듀티 사이클 사용 시 온돌 물 유량 밸브 주의 / Ondol water-flow valve note when using slow duty cycling (iparkapp gateway):** 싱크대 아래 (온돌 전동 밸브 옆) 에 있는 단지 전체용 **물 유량 밸브** (LPM 눈금이 표시되어 있는 경우가 많음) 를 기존 'low' 위치보다 약 3-4 배 (또는 'high' 위치) 로 열어두세요. 자세한 이유와 커미셔닝 절차는 [iPark 스마트홈 앱 가이드 — 슬로우 듀티 사이클 섹션](./guide/iparkapp.md#슬로우-듀티-사이클-제어--slow-duty-cycle-control) 참조.  
> *Open your apartment's **water-flow valve** (the single manual one, usually under the kitchen sink next to the ondol electric control valves; the dial is often LPM-marked) to roughly 3-4× its old "low" position (or "high" if unmarked). Full rationale + commissioning steps in the [iPark Smarthome App guide — slow duty-cycle section](./guide/iparkapp.md#슬로우-듀티-사이클-제어--slow-duty-cycle-control).*

- 추가 기기·속성이 필요하면 이슈 탭에 등록해 주세요. / *Open an issue if your household has devices not in the table above.*
- IPARK 스마트홈 클라우드 연동은 1.2.0 부터 지원됩니다. / *IPARK Smart Home cloud integration is supported from v1.2.0 onward.*
- iPark 스마트홈 앱 옵션은 본 포크에서 새로 추가되었습니다. / *The iPark Smarthome App option is new in this fork.*

## 기여 / Contributing

문제가 있나요? [Issues](https://github.com/dlxmax/ha-bestin-fork/issues) 탭에 작성해 주세요.  
*Found a bug? Please file an [issue](https://github.com/dlxmax/ha-bestin-fork/issues).*

- 테스트 중이며 다양한 환경에서의 검증이 필요합니다. / *Still under testing — coverage from more household configurations is welcome.*
- 월패드 버전 3.0 은 미테스트입니다. / *Wallpad 3.0 is not yet tested.*
- 시리얼 통신은 미테스트입니다. / *Serial communication has not been tested.*
- 좋은 아이디어가 있으면 [Pull requests](https://github.com/dlxmax/ha-bestin-fork/pulls) 환영합니다. / *Got a better idea? Open a [pull request](https://github.com/dlxmax/ha-bestin-fork/pulls).*
- 본 통합 사용으로 발생하는 문제에 대해 책임지지 않습니다. / *Use at your own risk — no warranty is provided.*

## 디버깅 / Debugging

문제 파악을 위해 아래 코드를 `configuration.yaml` 에 추가 후 Home Assistant 를 재시작하세요. 생성된 디버그 로그를 이슈 등록 시 첨부해 주시면 빠른 진단에 도움이 됩니다.  
*To investigate issues, add the snippet below to `configuration.yaml` and restart Home Assistant. Please attach the generated debug log when opening an issue.*

```yaml
logger:
  default: info
  logs:
    custom_components.bestin: debug
```
