import pytest


pytestmark = pytest.mark.asyncio


async def test_register_login_refresh_flow(app_client):
    r = await app_client.post("/auth/register", json={"email": "a@b.co", "password": "passw0rd!"})
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True
    assert body["data"]["email"] == "a@b.co"

    r = await app_client.post("/auth/login", json={"email": "a@b.co", "password": "passw0rd!"})
    assert r.status_code == 200
    tokens = r.json()["data"]
    assert "access_token" in tokens and "refresh_token" in tokens

    r = await app_client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert r.status_code == 200
    new_tokens = r.json()["data"]
    assert new_tokens["access_token"]


async def test_register_duplicate_email(app_client):
    payload = {"email": "dup@b.co", "password": "passw0rd!"}
    r1 = await app_client.post("/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await app_client.post("/auth/register", json=payload)
    assert r2.status_code == 409


async def test_login_wrong_password(app_client):
    await app_client.post("/auth/register", json={"email": "x@y.co", "password": "passw0rd!"})
    r = await app_client.post("/auth/login", json={"email": "x@y.co", "password": "wrongpass"})
    assert r.status_code == 401


async def test_unauthorized_scan_history(app_client):
    r = await app_client.get("/scan/history")
    assert r.status_code == 401
