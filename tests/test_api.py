from uuid import uuid4

from fastapi.testclient import TestClient

from apf.api import app

client = TestClient(app)


def payload(tenant_id):
    return {
        "tenant_id": str(tenant_id),
        "name": "MJN",
        "target_type": "OWNED_SYSTEM",
        "classification": "INTERNAL",
        "permissions": {"read": True, "parse": True, "derive": True, "publish_common_pattern": False},
        "source_evidence_ids": [str(uuid4())],
    }


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_tenant_isolation_and_revision():
    tenant = uuid4()
    created = client.post("/v1/targets", json=payload(tenant), headers={"X-Tenant-ID": str(tenant)})
    assert created.status_code == 201
    target_id = created.json()["id"]
    assert client.get(f"/v1/targets/{target_id}", headers={"X-Tenant-ID": str(uuid4())}).status_code == 404
    moved = client.post(
        f"/v1/targets/{target_id}/transitions?desired=AUTHORIZATION_PENDING",
        headers={"X-Tenant-ID": str(tenant), "If-Match": "0"},
    )
    assert moved.status_code == 200 and moved.json()["revision"] == 1


def test_prohibited_target_is_rejected():
    tenant = uuid4()
    data = payload(tenant)
    data["classification"] = "PROHIBITED"
    assert client.post("/v1/targets", json=data, headers={"X-Tenant-ID": str(tenant)}).status_code == 422

