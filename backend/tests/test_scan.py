import io

import pytest
from PIL import Image


pytestmark = pytest.mark.asyncio


def _png_bytes(size=(64, 64), color=(200, 100, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


async def _login(app_client, email="t@u.co"):
    await app_client.post("/auth/register", json={"email": email, "password": "passw0rd!"})
    r = await app_client.post("/auth/login", json={"email": email, "password": "passw0rd!"})
    return r.json()["data"]["access_token"]


async def test_submit_scan_creates_pending_job(app_client):
    token = await _login(app_client)
    r = await app_client.post(
        "/scan",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("img.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 202
    body = r.json()["data"]
    assert body["status"] == "pending"
    assert body["job_id"] and body["scan_id"]


async def test_submit_scan_rejects_non_image(app_client):
    token = await _login(app_client, "x@u.co")
    r = await app_client.post(
        "/scan",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("doc.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 415


async def test_history_pagination(app_client):
    token = await _login(app_client, "h@u.co")
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(3):
        await app_client.post(
            "/scan",
            headers=headers,
            files={"file": ("img.png", _png_bytes(), "image/png")},
        )
    r = await app_client.get("/scan/history?page=1&page_size=2", headers=headers)
    assert r.status_code == 200
    page = r.json()["data"]
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["page"] == 1


async def test_get_result_404_for_unknown_job(app_client):
    token = await _login(app_client, "n@u.co")
    r = await app_client.get(
        "/scan/result/does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
