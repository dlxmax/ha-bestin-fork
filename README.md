[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# BESTIN

BESTIN 월패드 1.0/2.0 사용자들을 위한 통합  
*Integration for users of the BESTIN wallpad versions 1.0 and 2.0*

이 포크에는 1.0 / 2.0 의 기존 RS-485 및 클라우드 연동 외에, 단지 중앙 서버 (i-parklife) 를 통해 작동하는 신규 'iPark 스마트홈 앱' 연동이 포함되어 있습니다. 자세한 내용은 [iPark 스마트홈 앱 가이드](./guide/iparkapp.md) 참조.  
*This fork adds a third "iPark Smarthome App" gateway that works through your apartment complex's central server (the same protocol the official Android app uses) — see the [iPark Smarthome App guide](./guide/iparkapp.md).*

### 추가 배경 / Why this fork exists

기존 두 가지 방식 (RS-485 / 웹사이트 기반 클라우드 연동) 은 본 포크 작성자의 가정에서 동작하지 않았습니다. 월패드는 RS-485 보다 오래된 RS-422 라인을 사용해 어댑터로 신호 해석이 어려웠고, 단지 웹사이트(`http://<단지IP>/`) 의 제어는 응답이 없었습니다. 반면 안드로이드 [iPark 스마트홈 앱](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet) 은 같은 단지 서버에서 정상 동작했습니다. 앱을 리버스 엔지니어링한 결과, 앱은 웹사이트와 동일한 URL 을 호출하지만 두 가지 핵심 차이가 있었습니다 — 정확한 PHP 경로 (`/webapp/data/...`) 와 필수 AJAX 헤더 (`X-Requested-With: XMLHttpRequest`). 본 'iPark 스마트홈 앱' 옵션은 이 두 가지 차이를 정확히 반영해 동일 단지 환경에서 안정적으로 동작합니다.  
*The two existing methods (RS-485 and the website-based cloud integration) didn't work in this fork's author's home — the wallpad uses the older RS-422 line so off-the-shelf adapters can't read it cleanly, and **the apartment website's controls (`http://<complex-IP>/`) silently dropped every command**. The Android [iPark Smarthome app](https://play.google.com/store/apps/details?id=com.mobiletalk.iparkhomenet) however works fine against the same server. Reverse-engineering the app revealed it hits the same server but with two critical differences from the website: the correct PHP path (`/webapp/data/...`) and a mandatory AJAX header (`X-Requested-With: XMLHttpRequest`). The new "iPark Smarthome App" option mirrors both, which makes it work reliably in homes where the website method does not.*

## 기여 / Contributing

문제가 있나요? [Issues](https://github.com/dlxmax/ha-bestin-fork/issues) 탭에 작성해 주세요.  
*Found a bug? Please file an [issue](https://github.com/dlxmax/ha-bestin-fork/issues).*

- 테스트 중이며, 다양한 환경에서의 테스트 케이스가 필요합니다.  
  *Still under testing — coverage from more household configurations is welcome.*
- 월패드 버전 3.0의 테스트 되지 않았으며 확인이 필요합니다. 도움이 필요하신 분은 이슈 및 디버깅 탭에 메일 주소로 연락 주세요.  
  *Wallpad 3.0 is not yet tested. If you can help, leave your contact info in the issues / debugging tab.*
- 시리얼 통신의 경우 테스트 되지 않았습니다.  
  *Serial communication has not been tested.*
- 더 좋은 아이디어가 있나요? [Pull requests](https://github.com/dlxmax/ha-bestin-fork/pulls)로 공유해 주세요!  
  *Got a better idea? Open a [pull request](https://github.com/dlxmax/ha-bestin-fork/pulls).*
- 이 통합을 사용하면서 발생하는 문제에 대해서는 책임지지 않습니다.  
  *Use at your own risk — no warranty is provided.*

## 설치 / Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dlxmax&repository=ha-bestin-fork&category=Integration)

이 통합을 설치하려면 이 GitHub Repo를 HACS Custom Repositories에 추가하거나 위의 배지를 클릭하세요. 설치 후 HomeAssistant를 재부팅하세요.  
*Add this GitHub repo to HACS Custom Repositories or click the badge above. Restart Home Assistant after install.*

1. **기기 및 서비스** 메뉴에서 **통합구성요소 추가하기**를 클릭합니다.  
   *In the **Devices & Services** menu, click **Add Integration**.*
2. **브랜드 이름 검색** 탭에 `BESTIN`을 입력하고 검색 결과에서 클릭합니다.  
   *Search for `BESTIN` and pick it from the results.*
3. 아래 설명에 따라 설정을 진행합니다 / *Then follow the option that matches your setup:*

   #### 1. 로컬 통신 설정 / Local communication
   - **IP 주소 / IP address** 입력 / *enter:*
     - **EW11** 사용 시: `192.168.x.x` 형식의 IP 주소 입력  
       *EW11: enter an IP address such as `192.168.x.x`*
     - **USB to 485** 사용 시: `/dev/ttyXXX` 경로 입력  
       *USB to 485: enter a `/dev/ttyXXX` path*
   - **포트 / Port** 입력 / *enter:*
     - **EW11** 사용 시: 포트 번호 입력 (기본값: 8899)  
       *EW11: port number (default 8899)*
     - **USB to 485** 사용 시: 이 항목은 생략합니다.  
       *USB to 485: leave this empty.*

   #### 2. 스마트홈 연동 설정 / Smart Home cloud integration
   - **스마트홈 연동**을 원할 경우, [center 가이드](./guide/center.md) 를 참고하여 설정을 구성합니다.  
     *For the official cloud integration, see the [center guide](./guide/center.md).*

   #### 3. iPark 스마트홈 앱 / iPark Smarthome App _(신규 / new)_
   - 단지 목록에서 자신의 단지를 선택하고, 앱과 동일한 아이디·비밀번호로 로그인합니다. IP 주소를 직접 입력할 필요도, 토큰을 복사할 필요도 없습니다.  
     *Pick your apartment complex from the auto-fetched directory, then sign in with the same username/password you use in the iPark Smarthome Android app — no IP entry, no token copy-paste.*
   - 자세한 내용은 [iPark 스마트홈 앱 가이드](./guide/iparkapp.md) 참조.  
     *See the [iPark Smarthome App guide](./guide/iparkapp.md) for details.*

4. 설정이 완료된 후, 컴포넌트가 로드되면 생성된 기기를 사용하실 수 있습니다.  
   *Once the integration finishes loading, the new devices will appear automatically.*

### 준비 / Prerequisites (RS-485 only)

iPark 스마트홈 앱 옵션은 별도의 하드웨어가 필요 없습니다. 아래 항목은 1번(로컬 RS-485) 옵션 한정입니다.  
*The iPark Smarthome App option needs no extra hardware. The list below applies only to option 1 (local RS-485).*

- EW11 or USB to 485 컨버터 2개 (게이트웨이 없는 일체형 세대는 한 개로 사용 가능)  
  *2× EW11 or USB-to-485 converters (1× is enough for gateway-less units).*
- 라인 확보 및 게이트웨이 타입 구분 (게이트웨이 있는 세대인지 월패드 뒤쪽 라인에 꼽히는지 확인)  
  *Confirm wiring and gateway type (with-gateway vs. plug into the line behind the wallpad).*
- 통신기 `EW11 or USB to 485` 설치 (자세한 내용은 [여기](./guide/install.md) 참조)  
  *Install the `EW11` or USB-to-485 adapter — see [install guide](./guide/install.md).*

  - 정상적으로 연결되었는지 확인하려면 시리얼 포트몬 프로그램을 통해 시리얼 데이터 확인. BESTIN 월패드의 경우 02로 시작하며 [예시 데이터](./guide/packet_dump.txt) 참조  
    *Verify the link with a serial port monitor — BESTIN frames start with `02`. See [sample data](./guide/packet_dump.txt).*
  - 디밍 세대의 경우 [해당](./guide/dimming_packet_dump.txt) 데이터 참조  
    *For dimming-light households, see the [dimming sample](./guide/dimming_packet_dump.txt).*

## 기능 / Features

![추가된 기기](./images/added_devices.png)

| 기기 / Device | 지원 / Supported | 속성 / Notes |
|---|---|---|
| 콘센트 / Outlet | O | 실시간 사용량, 대기전력자동차단 / Live usage, standby auto-cutoff |
| 조명 / Light | O | 디밍, 색온도 / Dimming, color temperature |
| 엘리베이터 / Elevator | O | 2.0의 경우 지원 / Supported on v2.0 |
| HEMS | O | 실시간, 총합 사용량 / Live + total usage |
| 환기 / Ventilation | O | 프리셋 (자연풍) / Presets (natural ventilation) |
| 가스 / Gas valve | O | 닫기 전용 (앱 동일) / Close-only (matches the app) |
| 도어락 / Door lock | O | 상태 표시만 (앱 동일) / Status only (matches the app) |
| 난방 / Heating | O | 5개 객실 + 지역난방 공급 온도 (있는 경우) / Up to 5 rooms + district heating supply temp (if present) |
| 외출 모드 / Away mode | O | iPark 스마트홈 앱 옵션 한정 / iPark Smarthome App option only |
| 에너지 모니터링 / Energy monitoring | O | 전기 / 가스 / 난방 / 온수 / 수도 — iPark 스마트홈 앱 옵션 한정 / Electric/Gas/Heat/Hot water/Water — iPark Smarthome App option only |

- 추가 기기나 속성이 필요하면 이슈 탭에 등록해 주세요.  
  *Open an issue if your household has devices not in the table above.*
- 1.2.0 버전 이후부터 IPARK 스마트홈 연동을 지원합니다.  
  *IPARK Smart Home cloud integration is supported from v1.2.0 onward.*
- iPark 스마트홈 앱 (앱과 동일 프로토콜) 옵션은 이 포크에서 새로 추가되었습니다.  
  *The iPark Smarthome App option (same protocol as the official Android app) is new in this fork.*

## 디버깅 / Debugging

문제 파악을 위해 아래 코드를 `configuration.yaml` 파일에 추가 후 HomeAssistant를 재시작해 주세요.  
*To investigate issues, add the snippet below to your `configuration.yaml` and restart Home Assistant.*

BESTIN 구성요소의 디버그 로깅을 활성화하고 생성된 파일을 이슈 등록 시 첨부해 주세요.  
*This enables debug logging for the BESTIN component — please attach the generated log file when you open an issue.*

```yaml
logger:
  default: info
  logs:
    custom_components.bestin: debug
```
