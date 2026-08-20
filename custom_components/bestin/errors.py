"""연동 공통 예외 — Exceptions shared across the BESTIN gateways.

단지 서버가 죽었을 때와 자격 증명이 틀렸을 때는 대응이 완전히 다릅니다.
전자는 기다렸다 다시 시도해야 하고, 후자는 사용자가 다시 입력해야만 풀립니다.
v1.4.12 까지는 두 경우 모두 ``RuntimeError`` 하나로 뭉뚱그려져 HA 로그에
'Error setting up entry' 만 남았습니다.

The central server being down and the password being wrong need opposite
handling: one should be retried on a timer, the other never recovers on its
own. Through v1.4.12 both collapsed into a single ``RuntimeError``, which HA
surfaced as a bare "Error setting up entry".
"""

from __future__ import annotations


class BestinIparkAppError(Exception):
    """iParkApp 게이트웨이 오류의 기반 클래스 — Base for iParkApp failures."""


class IparkAppConnectionError(BestinIparkAppError):
    """서버 접속 실패 — The complex server is unreachable or misbehaving.

    타임아웃, 접속 거부, 5xx 응답, 로그인 JSON 이 성공이 아닌 경우 모두
    여기에 해당합니다. 재시도로 복구될 수 있는 상태입니다.

    Timeouts, refused connections, 5xx replies and non-success login payloads
    that do not look like a credential rejection. Recoverable by retrying.
    """


class IparkAppAuthError(BestinIparkAppError):
    """자격 증명 거부 — The server rejected the username/password.

    재시도해도 같은 결과이므로 사용자가 다시 설정해야 합니다.

    Retrying changes nothing; the user has to re-enter their credentials.
    """
