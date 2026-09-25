from apf.macol_readiness import MacolEvidence, assess_macol_trial


def test_browser_demo_cannot_be_promoted_to_010_success():
    result = assess_macol_trial(MacolEvidence(both_sides_synchronized=True))
    assert result.status == "FAIL"
    assert "기본 전화 앱에서 일반 010 발신" in result.unmet


def test_install_or_extra_role_fails_even_when_popup_works():
    result = assess_macol_trial(MacolEvidence(
        card_opened_once=True,
        ordinary_dialer_call=True,
        caller_installed_app=True,
        caller_granted_role_or_permission=True,
        caller_screen_opened_automatically=True,
        screen_available_during_connected_call=True,
        both_sides_synchronized=True,
        device_and_network_recorded=True,
    ))
    assert result.status == "FAIL"
    assert "발신자 앱 설치 없음" in result.unmet


def test_evidence_is_scoped_to_tested_pair_only():
    result = assess_macol_trial(MacolEvidence(**{
        "card_opened_once": True,
        "ordinary_dialer_call": True,
        "caller_screen_opened_automatically": True,
        "screen_available_during_connected_call": True,
        "both_sides_synchronized": True,
        "device_and_network_recorded": True,
    }))
    assert result.status == "PASS"
    assert "tested" in result.scope
