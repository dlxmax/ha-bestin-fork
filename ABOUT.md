# 프로젝트 소개 / About

**ha-bestin-fork** 는 한국 BESTIN / 현대 IPARK 월패드를 [Home Assistant](https://www.home-assistant.io/) 에 연동하기 위한 커스텀 컴포넌트입니다. 본 포크는 같은 단지에서도 동작하지 않던 기존 두 가지 방식을 보완하기 위해 세 번째 옵션을 추가합니다.  
*ha-bestin-fork is a Home Assistant custom component for the Korean BESTIN / Hyundai IPARK wallpads. This fork adds a third gateway option that fills the gap when the two existing methods don't work in a given complex.*

## 한 줄 요약 / One-line summary

월패드 → Home Assistant. 세 가지 연결 방식 중 본인 단지에 맞는 것을 선택할 수 있습니다.  
*Wallpad → Home Assistant. Pick whichever of the three connection methods works in your complex.*

## 방식 비교 / Method comparison

| 방식 / Method | 무엇을 하는가 / What it does | 장점 / Pros | 단점 / Cons |
|---|---|---|---|
| **로컬 RS-485 / Local RS-485** | 월패드 후면 라인을 EW11 또는 USB-RS485 어댑터로 직접 연결.<br>*Direct line tap with EW11 or a USB-to-RS-485 adapter.* | 인터넷 / 단지 서버 의존 없음<br>*Zero internet / server dependency* | 하드웨어 필요 · RS-422 구형 월패드는 신호 해석 불가 · 시리얼은 미테스트<br>*Needs hardware; older RS-422 wallpads can't be parsed; serial untested* |
| **IPARK 스마트홈 클라우드 / IPARK Smart Home cloud** | 현대 클라우드 (`center.hdc-smart.com`) 와 통신 (Smart Home v1 / v2).<br>*Talks to the official cloud (`center.hdc-smart.com`).* | 하드웨어 불필요 · 신축·중형 단지에서 안정적<br>*No hardware; stable on newer complexes* | UUID 등록 절차 복잡 · 일부 구형 단지에서 무반응<br>*UUID registration is fiddly; unresponsive on some older complexes* |
| **iPark 스마트홈 앱 / iPark Smarthome App** _(신규 / new)_ | 단지 중앙 서버 (예: `220.79.141.134`) 와 안드로이드 앱과 동일한 방식으로 통신.<br>*Talks to the apartment complex's central server the same way the Android app does.* | 토큰 복사 불필요 · 단지 이름만으로 설정 · 웹사이트 제어가 무반응이던 가정에서도 동작<br>*No token; pick the complex by name; works where the website-controls silently fail* | 단지 중앙 서버가 살아 있어야 함<br>*Requires the complex's central server to be online* |

## 무엇이 새로워졌는가 / What's new in this fork

본 포크는 기존 두 가지 옵션 (로컬 RS-485, IPARK 스마트홈 클라우드) 의 코드를 그대로 유지한 채 세 번째 옵션 'iPark 스마트홈 앱' 만 **추가**합니다. 기존 사용자에게는 어떠한 동작 변화도 없습니다.  
*This fork strictly **adds** the third "iPark Smarthome App" option without touching any existing code paths. Users of the previous two methods see no behavioural change.*

## 왜 만들었는가 / Why this exists

본 포크 작성자의 가정에서는 두 기존 방식이 모두 동작하지 않았습니다. 월패드는 RS-422 라인을 사용해 RS-485 어댑터로 신호 해석이 어려웠고, 단지 웹사이트의 제어 명령은 응답 없이 사라졌습니다. 그러나 같은 서버에 안드로이드 [iPark 스마트홈 앱](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet) 을 사용하면 정상 동작했습니다. 앱을 정적 분석한 결과, 앱은 웹사이트와 같은 URL 을 호출하지만 두 가지 핵심 차이가 있었습니다 — 정확한 PHP 경로 (`/webapp/data/...`) 와 필수 AJAX 헤더 (`X-Requested-With: XMLHttpRequest`). 헤더 누락 시 서버는 즉시 `result="timeout"` 더미 응답을 돌려보냅니다 — 웹사이트가 무반응이었던 직접적인 원인입니다. 본 신규 옵션은 두 차이를 정확히 반영합니다.  
*Both existing methods failed in this fork author's home — the wallpad uses RS-422 (older than RS-485) so adapters couldn't parse it cleanly, and the apartment-complex website silently dropped every control command. The Android iPark Smarthome app worked fine on the same server. Static analysis of the APK revealed the app makes near-identical calls to the website but with two critical differences: the correct PHP path (`/webapp/data/...`) and the mandatory `X-Requested-With: XMLHttpRequest` header. Without that header the server short-circuits with a stub `result="timeout"` — the direct cause of the website's silent failures. The new option mirrors both differences faithfully.*

## 지원 기기 / Supported devices

거실 조명, 각실 조명, 콘센트 (대기전력 자동차단 포함), 난방 (객실 + 지역난방 공급 온도 센서), 가스밸브 (닫기 전용), 환기 (속도 포함), 외출 모드, 도어락 (상태만), 에너지 모니터링 (전기 / 가스 / 난방 / 온수 / 수도), 엘리베이터 호출 (해당 옵션 한정).  
*Living-room lights, per-room lights, outlets (with standby cutoff), thermostats (per-room + district-heating supply-temp sensor), gas valve (close-only), ventilation (with speeds), away mode, doorlock (status only), energy monitoring (Electric / Gas / Heat / Hot water / Water), elevator call (where supported).*

## 다국어 지원 / Localisation

이 통합과 모든 문서는 한국어와 영어를 동시 지원합니다 (한국어 우선).  
*The integration and all documentation are bilingual — Korean first, English second.*

## 라이선스 / License

원본 [`fxnnxc/ha-bestin`](https://github.com/fxnnxc/ha-bestin) 의 라이선스를 따릅니다.  
*Follows the upstream [`fxnnxc/ha-bestin`](https://github.com/fxnnxc/ha-bestin) license.*

## 감사의 말 / Acknowledgments

- [@fxnnxc](https://github.com/fxnnxc) — 원본 통합 작성자.<br>*Original integration author.*
- [Mobiletalk](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet) — 안드로이드 iPark 스마트홈 앱 개발사 (앱의 호출 패턴을 분석해 본 통합을 구현).<br>*Developer of the Android iPark Smarthome app (whose call pattern this fork mirrors).*

## 더 알아보기 / Learn more

- [README.md](./README.md) — 설치 / 설정 / 디버깅 / *install, setup, debugging*
- [guide/iparkapp.md](./guide/iparkapp.md) — iPark 스마트홈 앱 옵션 상세 / *iPark Smarthome App option in detail*
- [guide/center.md](./guide/center.md) — 기존 클라우드 옵션 (1.0 / 2.0) / *existing cloud option (v1.0 / v2.0)*
- [guide/install.md](./guide/install.md) — RS-485 어댑터 설치 / *RS-485 adapter install*
