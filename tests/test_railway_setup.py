from uuid import uuid4

from fastapi.testclient import TestClient

from apf.api import create_app
from apf.console import ConsoleSecurity
from apf.repository import MemoryRepository


def test_railway_guide_requires_owner_and_preserves_deployment_lock():
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(
            environment="test", secret="s" * 32, allow_dev_sessions=True,
        ),
    )
    client = TestClient(app, base_url="https://testserver")
    assert client.get("/console/railway-setup").status_code == 401
    assert client.get("/v1/console/railway-readiness").status_code == 401
    assert client.get("/v1/console/railway-guidance").status_code == 401
    assert client.get("/v1/console/railway-live").status_code == 401
    client.post(
        "/console/dev/session",
        json={"tenant_id": str(uuid4()), "principal_id": str(uuid4()), "role": "operator"},
    )
    assert client.get("/console/railway-setup").status_code == 403
    assert client.get("/v1/console/railway-readiness").status_code == 403
    assert client.get("/v1/console/railway-guidance").status_code == 403
    assert client.get("/v1/console/railway-live").status_code == 403
    client.post(
        "/console/dev/session",
        json={"tenant_id": str(uuid4()), "principal_id": str(uuid4()), "role": "owner"},
    )
    page = client.get("/console/railway-setup")
    assert page.status_code == 200
    assert "결과물 확인과 운영 준비" in page.text
    assert "지금 확인할 수 있는 결과물" in page.text
    assert "다음 개발 단계" in page.text
    assert page.text.index("지금 확인할 수 있는 결과물") < page.text.index("단계별 진행")
    assert "사용자 자가 확인" in page.text
    assert "아르카온의 Railway 경험 판단" in page.text
    assert "Railway 실시간 상태" in page.text
    assert page.headers["cache-control"] == "no-store"
    status = client.get("/v1/console/railway-readiness")
    assert status.status_code == 200
    assert status.json() == {
        "overall_status": "PRODUCT_IMPLEMENT_HOLD", "deployment_allowed": False,
    }
    guidance = client.get("/v1/console/railway-guidance")
    assert guidance.headers["cache-control"] == "no-store"
    result = guidance.json()
    assert result["decision"] == "RECHECK_AND_HOLD"
    assert result["observation_is_live"] is False
    assert result["automated_railway_write"] is False
    assert result["historical_observation"]["railway_change_count"].startswith("Apply 4")
    assert len(result["phases"]) == 7
    assert "production branch is auto-connected to main while deployment lock remains false" in result["phases"][3]["hold_when"]
    assert client.get("/v1/console/railway-live").status_code == 503
    csrf = client.cookies["apf_console_csrf"]
    locked = client.post("/v1/console/railway-service-create", headers={"X-CSRF-Token": csrf},
                         json={"approval_token": "a" * 40})
    assert locked.status_code == 423
