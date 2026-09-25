"""Evidence gate for MACOL's one-click card and ordinary 010-call experience.

This is a product assessment, not a telecom integration or a device detector.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MacolEvidence(BaseModel):
    """Results of a controlled trial on the actual caller and receiver devices."""

    card_opened_once: bool = False
    ordinary_dialer_call: bool = False
    caller_installed_app: bool = False
    caller_granted_role_or_permission: bool = False
    caller_tapped_link_or_notification: bool = False
    caller_screen_opened_automatically: bool = False
    screen_available_during_connected_call: bool = False
    both_sides_synchronized: bool = False
    device_and_network_recorded: bool = False


class MacolReadiness(BaseModel):
    status: Literal["PASS", "FAIL", "NOT_TESTED"]
    unmet: list[str]
    scope: str = "One tested caller/receiver/device/network combination only"


def assess_macol_trial(evidence: MacolEvidence | None) -> MacolReadiness:
    """Do not promote browser or installed-app demos to ordinary-call success."""
    if evidence is None:
        return MacolReadiness(status="NOT_TESTED", unmet=["실기기 증거 없음"])
    checks = {
        "명함 최초 열람 1회": evidence.card_opened_once,
        "기본 전화 앱에서 일반 010 발신": evidence.ordinary_dialer_call,
        "발신자 앱 설치 없음": not evidence.caller_installed_app,
        "발신자 추가 권한·전화 역할 지정 없음": not evidence.caller_granted_role_or_permission,
        "발신자 추가 링크·알림 터치 없음": not evidence.caller_tapped_link_or_notification,
        "발신자 화면 자동 표시": evidence.caller_screen_opened_automatically,
        "통화 연결 후 화면 유지": evidence.screen_available_during_connected_call,
        "양측 메뉴 실시간 동기화": evidence.both_sides_synchronized,
        "단말·통신망 조건 기록": evidence.device_and_network_recorded,
    }
    unmet = [name for name, passed in checks.items() if not passed]
    return MacolReadiness(status="FAIL" if unmet else "PASS", unmet=unmet)
