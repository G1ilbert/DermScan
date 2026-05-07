import pytest

pytestmark = pytest.mark.asyncio


async def test_register_returns_supabase_session(app_client):
    r = await app_client.post("/auth/register", json={"email": "a@b.co", "password": "passw0rd!"})
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["access_token"].startswith("fake-access::")
    assert data["refresh_token"].startswith("fake-refresh::")
    assert data["user_id"]
    assert data["email"] == "a@b.co"


async def test_login_returns_supabase_session(app_client):
    await app_client.post("/auth/register", json={"email": "l@b.co", "password": "passw0rd!"})
    r = await app_client.post("/auth/login", json={"email": "l@b.co", "password": "passw0rd!"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["access_token"].startswith("fake-access::")


async def test_register_duplicate_email(app_client):
    payload = {"email": "dup@b.co", "password": "passw0rd!"}
    r1 = await app_client.post("/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await app_client.post("/auth/register", json=payload)
    assert r2.status_code == 400


async def test_login_wrong_password(app_client):
    await app_client.post("/auth/register", json={"email": "x@y.co", "password": "passw0rd!"})
    r = await app_client.post("/auth/login", json={"email": "x@y.co", "password": "wrongpass"})
    assert r.status_code == 401


async def test_unauthorized_scan_history(app_client):
    r = await app_client.get("/scan/history")
    assert r.status_code == 401


async def test_me_returns_user_after_register(app_client):
    reg = await app_client.post("/auth/register", json={"email": "m@b.co", "password": "passw0rd!"})
    token = reg.json()["data"]["access_token"]
    r = await app_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    me = r.json()["data"]
    assert me["email"] == "m@b.co"
