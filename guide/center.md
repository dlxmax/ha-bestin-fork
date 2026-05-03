# IPARK 스마트홈 연동 가이드 / IPARK Smart Home Integration Guide

이 가이드는 기존 두 가지 방식 (1.0 / 2.0) 의 설정 방법을 안내합니다. 단지 중앙 서버를 통해 동작하는 신규 'iPark 스마트홈 앱' 옵션은 [iPark 스마트홈 앱 가이드](./iparkapp.md) 를 참고하세요.  
*This guide covers the two existing methods (v1.0 and v2.0). For the new "iPark Smarthome App" option that talks to the apartment complex's central server, see the [iPark Smarthome App guide](./iparkapp.md).*

## Step 1 — 버전 식별 / Identify your version

**월패드로 구분 / By wallpad model**

서버 버전을 선택해야 합니다. 보통은 월패드 버전을 따라갑니다. 간혹 세대 단위로 월패드를 교체했거나 게이트웨이를 변경한 경우, 현재 설치된 월패드 버전을 기준으로 하시면 됩니다.  
*You'll need to choose the server version. Normally it matches your wallpad version. If your household swapped the wallpad or changed the gateway, go by whatever wallpad is currently installed.*

**앱으로 구분 / By app**

대중적으로 사용하는 앱을 예시로 [해당 앱은 2.0](https://apps.apple.com/kr/app/%EC%95%84%EC%9D%B4%ED%8C%8C%ED%81%AC-%EC%8A%A4%EB%A7%88%ED%8A%B8%ED%99%882-0/id1435034391) 처럼 앱 이름으로 구분 가능합니다. 1.0 의 경우 따로 버전이 붙지 않습니다 (`IPARK 스마트홈` 등).  
*You can also tell by which app you use — names like ["IPARK 스마트홈 2.0"](https://apps.apple.com/kr/app/%EC%95%84%EC%9D%B4%ED%8C%8C%ED%81%AC-%EC%8A%A4%EB%A7%88%ED%8A%B8%ED%99%882-0/id1435034391) signal v2.0; v1.0 apps just say `IPARK 스마트홈` with no version suffix.*

이후 찾은 버전을 항목에서 선택해 주세요. 3.0 의 경우 지원하지 않습니다 (REST API 레퍼런스가 없습니다).  
*Pick the version you identified. Version 3.0 is not supported (no REST API reference is available).*

## Step 2 — 각 버전별 구성 / Per-version configuration

### Version 1.0

| 필드 / Field | 설명 / Description |
|---|---|
| IP 주소 / IP address | 단지 서버 IP 주소. [i-parklife.com](http://www.i-parklife.com/) 에서 본인 아파트를 찾고, 아파트 이름을 클릭하면 서버 원격 주소로 리디렉션됩니다. 그 IP 를 입력하세요.<br>*Apartment server IP. Visit [i-parklife.com](http://www.i-parklife.com/), find your complex, click its name to be redirected to the remote server, then enter that IP here.* |
| 사용자 이름 / Username | 원격 주소 로그인 아이디 (또는 스마트홈 앱 계정).<br>*Login ID for the remote server (same as the smart-home app account).* |
| 비밀번호 / Password | 위 계정의 비밀번호.<br>*Password for that account.* |

> 💡 IP 입력이 번거로우시면, 단지 이름을 드롭다운에서 바로 선택할 수 있는 신규 [iPark 스마트홈 앱 옵션](./iparkapp.md) 도 시도해 보세요.  
> *Tip: if entering IPs by hand is annoying, try the new [iPark Smarthome App option](./iparkapp.md) that picks the complex from a dropdown.*

### Version 2.0

| 필드 / Field | 설명 / Description |
|---|---|
| 사이트 주소 / Site URL | UUID 등록 시 인자로 사용됩니다. [center.hdc-smart.com/v3/auth/valley](https://center.hdc-smart.com/v3/auth/valley) 에서 본인 아파트를 찾아 `code` / `url` 을 기억해 두세요.<br>*Used as an argument when registering the UUID. Find your complex on [center.hdc-smart.com/v3/auth/valley](https://center.hdc-smart.com/v3/auth/valley) and note its `code` / `url`.* |
| IP 주소 (선택) / IP address (optional) | 서버를 통한 REST 엘리베이터 호출이 필요한 경우에만 세대 내 월패드 IP 주소를 입력합니다 (층수·방향 센서 지원).<br>*Required only for REST elevator integration (provides floor/direction sensors).* |
| UUID | 월패드에 등록된 고유 ID. 등록 방법은 아래 절차 참조.<br>*Wallpad's unique device ID — see the registration steps below.* |

월패드 관리자 모드 진입:  
*To enter wallpad admin mode:*

```
설정 5초 누르기 / Hold Settings for 5 seconds
인증번호: 70375968 또는 73075968 / Auth code: 70375968 or 73075968
설정 페이지: 5968 / Settings page: 5968
```

UUID 등록 절차 / UUID registration:

1. 월패드에서 **모바일 기기 등록** 을 누릅니다. / *On the wallpad, tap **Register mobile device**.*
2. [Google Colab](https://colab.research.google.com/drive/179PCxJUr2HU07SzkSt-z-JTqMbHT1Smv?hl=ko) 에 접속합니다. / *Open the [Google Colab notebook](https://colab.research.google.com/drive/179PCxJUr2HU07SzkSt-z-JTqMbHT1Smv?hl=ko).*
3. 좌측에 총 3개의 실행 버튼이 표시됩니다. / *You'll see three run buttons in the left margin.*
4. 월패드의 등록 창이 활성화된 상태에서 첫 번째 버튼을 누릅니다. (UUID 는 고유 ID 이므로 원하는 값으로 변경하세요.) / *With the wallpad's registration screen active, click the first button. (You can change the UUID to anything unique.)*
5. 월패드에서 6 자리 인증 번호가 출력되고, Colab 페이지에는 코드가 출력됩니다. / *The wallpad shows a 6-digit auth code; Colab shows a transaction code.*
6. 출력된 코드를 `transaction` 에 입력하고, 월패드의 인증 번호를 `password` 에 입력합니다. / *Paste the transaction code into `transaction` and the wallpad's auth number into `password`.*
7. 두 번째 버튼을 누릅니다. / *Click the second button.*
8. 마지막으로 세 번째 버튼을 누르면 등록이 성공합니다. / *Click the third button — registration is now complete.*
