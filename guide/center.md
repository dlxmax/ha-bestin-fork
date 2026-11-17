# IPARK 스마트홈 연동 가이드 / IPARK Smart Home Integration Guide

이 가이드는 기존 두 가지 방식(1.0 / 2.0)의 설정 방법을 안내해요. 단지 중앙 서버를 통해 동작하는 새 'iPark 스마트홈 앱' 옵션은 [iPark 스마트홈 앱 가이드](./iparkapp.md)를 참고하세요.  
*This guide covers the two existing methods (v1.0 and v2.0). For the new "iPark Smarthome App" option that talks to the apartment complex's central server, see the [iPark Smarthome App guide](./iparkapp.md).*

## Step 1: 버전 식별 / Identify your version

**월패드로 구분 / By wallpad model**

서버 버전을 골라야 해요. 보통은 월패드 버전을 따라가요. 세대에서 월패드를 바꿨거나 게이트웨이를 변경했다면, 지금 설치된 월패드 버전을 기준으로 하면 돼요.  
*You'll need to choose the server version. Normally it matches your wallpad version. If your household swapped the wallpad or changed the gateway, go by whatever wallpad is currently installed.*

**앱으로 구분 / By app**

대중적으로 사용하는 앱을 예시로 [해당 앱은 2.0](https://apps.apple.com/kr/app/%EC%95%84%EC%9D%B4%ED%8C%8C%ED%81%AC-%EC%8A%A4%EB%A7%88%ED%8A%B8%ED%99%882-0/id1435034391)처럼 앱 이름으로 구분할 수 있어요. 1.0은 따로 버전이 붙지 않아요 (`IPARK 스마트홈` 등).  
*You can also tell by which app you use — names like ["IPARK 스마트홈 2.0"](https://apps.apple.com/kr/app/%EC%95%84%EC%9D%B4%ED%8C%8C%ED%81%AC-%EC%8A%A4%EB%A7%88%ED%8A%B8%ED%99%882-0/id1435034391) signal v2.0; v1.0 apps just say `IPARK 스마트홈` with no version suffix.*

그다음 찾은 버전을 항목에서 고르세요. 3.0은 지원하지 않아요(REST API 레퍼런스가 없어요).  
*Pick the version you identified. Version 3.0 is not supported (no REST API reference is available).*

## Step 2: 버전별 설정 / Per-version configuration

### Version 1.0

| 필드 / Field | 설명 / Description |
|---|---|
| IP 주소 / IP address | 단지 서버 IP 주소. [i-parklife.com](http://www.i-parklife.com/)에서 본인 아파트를 찾고, 아파트 이름을 클릭하면 서버 원격 주소로 넘어가요. 그 IP를 입력하세요.<br>*Apartment server IP. Visit [i-parklife.com](http://www.i-parklife.com/), find your complex, click its name to be redirected to the remote server, then enter that IP here.* |
| 사용자 이름 / Username | 원격 주소 로그인 아이디(또는 스마트홈 앱 계정).<br>*Login ID for the remote server (same as the smart-home app account).* |
| 비밀번호 / Password | 위 계정의 비밀번호.<br>*Password for that account.* |

> 💡 IP 입력이 번거로우시면, 단지 이름을 드롭다운에서 바로 선택할 수 있는 신규 [iPark 스마트홈 앱 옵션](./iparkapp.md)도 시도해 보세요.  
> *Tip: if entering IPs by hand is annoying, try the new [iPark Smarthome App option](./iparkapp.md) that picks the complex from a dropdown.*

### Version 2.0

| 필드 / Field | 설명 / Description |
|---|---|
| 사이트 주소 / Site URL | UUID를 등록할 때 인자로 써요. [center.hdc-smart.com/v3/auth/valley](https://center.hdc-smart.com/v3/auth/valley)에서 본인 아파트를 찾아 `code` / `url`을 기억해 두세요.<br>*Used as an argument when registering the UUID. Find your complex on [center.hdc-smart.com/v3/auth/valley](https://center.hdc-smart.com/v3/auth/valley) and note its `code` / `url`.* |
| 엘리베이터 수 / Elevator number | 우리 세대가 쓰는 엘리베이터 수(1~4). 엘리베이터마다 층수·방향 센서와 'Elevator down' 스위치가 하나씩 생겨요. 둘 이상이면 'Elevator down 1', 'Elevator down 2'처럼 번호가 붙어요.<br>*How many elevators serve your home (1 to 4). Each one gets a floor sensor, a direction sensor and an "Elevator down" switch. With more than one, the switches are numbered: "Elevator down 1", "Elevator down 2".* |
| IP 주소 (선택) / IP address (optional) | 엘리베이터를 쓸 때만 세대 월패드 IP 주소를 입력하세요. 비워 두면 엘리베이터 엔티티가 생기지 않아요.<br>*Only needed for the elevator: enter your wallpad's IP address. Leave it empty and no elevator entities are created.* |
| UUID | 월패드에 등록된 고유 ID. 등록 방법은 아래 절차를 보세요.<br>*Wallpad's unique device ID — see the registration steps below.* |

월패드 관리자 모드 진입:  
*To enter wallpad admin mode:*

```
설정 5초 누르기 / Hold Settings for 5 seconds
인증번호: 70375968 또는 73075968 / Auth code: 70375968 or 73075968
설정 페이지: 5968 / Settings page: 5968
```

UUID 등록 절차 / UUID registration:

1. 월패드에서 **모바일 기기 등록**을 누르세요. / *On the wallpad, tap **Register mobile device**.*
2. [Google Colab](https://colab.research.google.com/drive/179PCxJUr2HU07SzkSt-z-JTqMbHT1Smv?hl=ko)에 접속하세요. / *Open the [Google Colab notebook](https://colab.research.google.com/drive/179PCxJUr2HU07SzkSt-z-JTqMbHT1Smv?hl=ko).*
3. 좌측에 실행 버튼 3개가 보여요. / *You'll see three run buttons in the left margin.*
4. 월패드의 등록 창이 활성화된 상태에서 첫 번째 버튼을 누르세요. (UUID는 고유 ID이므로 원하는 값으로 변경하세요.) / *With the wallpad's registration screen active, click the first button. (You can change the UUID to anything unique.)*
5. 월패드에서 6자리 인증 번호가 출력되고, Colab 페이지에는 코드가 나와요. / *The wallpad shows a 6-digit auth code; Colab shows a transaction code.*
6. 출력된 코드를 `transaction`에 입력하고, 월패드의 인증 번호를 `password`에 입력하세요. / *Paste the transaction code into `transaction` and the wallpad's auth number into `password`.*
7. 두 번째 버튼을 누르세요. / *Click the second button.*
8. 마지막으로 세 번째 버튼을 누르면 등록이 끝나요. / *Click the third button — registration is now complete.*

### 엘리베이터 / Elevator

'Elevator down' 스위치와 'Elevator up' 스위치로 엘리베이터를 불러요. 공식 앱의 '하향 호출', '상향 호출'과 같아요. 'Elevator down' 스위치는 엘리베이터마다 하나씩 있지만, 어느 것을 켜도 같은 호출을 보내요.  
*Call the elevator with the "Elevator down" and "Elevator up" switches, the same as "call down" and "call up" in the official app. There is one "Elevator down" switch per elevator, but each one sends the same call.*

층수·방향 센서는 서버가 엘리베이터 위치를 보내 줄 때만 동작해요. 일부 단지(hdc-smart.com 서버)는 보내 주지 않아서 센서가 '사용할 수 없음'으로 나와요. 공식 앱도 층수와 방향은 보여 주지 않아요. 호출은 그대로 돼요.  
*The floor and direction sensors only work when the server sends the elevator's position. Some complexes (hdc-smart.com servers) don't, so the sensors show as unavailable. The official app doesn't show floor or direction either. Calling still works.*
