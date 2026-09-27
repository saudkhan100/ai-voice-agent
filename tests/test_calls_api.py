from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app

VALID = {
    "phone": "+14165550123",
    "first_name": "Sam",
    "vehicle": {"make": "Toyota", "model": "RAV4"},
}


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_start_call_requires_api_key() -> None:
    async with client() as c:
        resp = await c.post("/api/calls", json=VALID)
    assert resp.status_code == 401


async def test_start_call_rejects_bad_phone() -> None:
    headers = {"X-API-Key": get_settings().lead_api_key}
    async with client() as c:
        resp = await c.post("/api/calls", json=VALID | {"phone": "416-555"}, headers=headers)
    assert resp.status_code == 422
    assert "E.164" in resp.text


async def test_twilio_webhook_rejects_unsigned_request() -> None:
    async with client() as c:
        resp = await c.post("/twilio/status/1", data={"CallStatus": "completed"})
    assert resp.status_code == 403
