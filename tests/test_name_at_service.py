from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from apf.name_at_service import install_name_at


def test_complete_private_to_public_flow(tmp_path: Path):
    app = FastAPI()
    install_name_at(app, root=tmp_path, origin="https://profiles.example", secret="x" * 32)
    with TestClient(app, base_url="https://profiles.example") as client:
        assert client.post("/name-at/register", json={"username": "maker", "password": "long password 123"}).status_code == 200
        login = client.post("/name-at/login", json={"username": "maker", "password": "long password 123"})
        csrf = login.json()["csrf_token"]
        buffer = BytesIO()
        Image.new("RGB", (2, 2), "blue").save(buffer, format="PNG")
        png = buffer.getvalue()
        upload = client.post("/name-at/media", content=png, headers={"X-CSRF-Token": csrf})
        assert upload.status_code == 200
        image_id = upload.json()["id"]
        client.cookies.clear()
        assert client.get(f"/name-at/media/{image_id}").status_code == 401
        login = client.post("/name-at/login", json={"username": "maker", "password": "long password 123"})
        csrf = login.json()["csrf_token"]
        draft = client.post("/name-at/profiles", headers={"X-CSRF-Token": csrf}, json={
            "display_name": "홍길동", "introduction": "목공 작업",
            "image_ids": [image_id], "image_descriptions": ["작업 사진"],
        })
        assert draft.status_code == 200, draft.text
        item = draft.json()
        assert client.get(f"/p/{item['id']}").status_code == 404
        assert client.post(f"/name-at/profiles/{item['id']}/publish", json={
            "expected_revision": item["revision"], "approved_digest": item["approval_digest"],
        }).status_code == 403
        publish = client.post(f"/name-at/profiles/{item['id']}/publish",
            headers={"X-CSRF-Token": csrf}, json={
                "expected_revision": item["revision"], "approved_digest": item["approval_digest"],
            })
        assert publish.status_code == 200, publish.text
        assert publish.json()["discovery"][0]["status"] == "setup_required"
        assert client.get(f"/p/{item['id']}").status_code == 200
        client.cookies.clear()
        assert client.get(f"/name-at/media/{image_id}").status_code == 200
        login = client.post("/name-at/login", json={"username": "maker", "password": "long password 123"})
        csrf = login.json()["csrf_token"]
        assert "홍길동" in client.get("/name-at/find?q=홍길동@").text
        assert "홍길동@" in client.get("/at/홍길동").text
        assert item["id"] in client.get("/sitemap.xml").text
        client.post(f"/name-at/profiles/{item['id']}/withdraw", headers={"X-CSRF-Token": csrf})
        assert client.get(f"/p/{item['id']}").status_code == 404


def test_uploaded_media_cannot_be_used_by_other_account(tmp_path: Path):
    app = FastAPI()
    install_name_at(app, root=tmp_path, origin="https://profiles.example", secret="x" * 32)
    with TestClient(app, base_url="https://profiles.example") as client:
        for name in ("owner", "other"):
            client.post("/name-at/register", json={"username": name, "password": "long password 123"})
        csrf = client.post("/name-at/login", json={"username": "owner", "password": "long password 123"}).json()["csrf_token"]
        buffer = BytesIO()
        Image.new("RGB", (2, 2), "red").save(buffer, format="JPEG")
        item = client.post("/name-at/media", content=buffer.getvalue(), headers={"X-CSRF-Token": csrf}).json()
        csrf = client.post("/name-at/login", json={"username": "other", "password": "long password 123"}).json()["csrf_token"]
        response = client.post("/name-at/profiles", headers={"X-CSRF-Token": csrf}, json={
            "display_name": "홍길동", "introduction": "소개", "image_ids": [item["id"]],
            "image_descriptions": ["사진"],
        })
        assert response.status_code == 403
