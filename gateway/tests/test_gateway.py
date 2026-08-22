import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "quant-gateway"
    assert "market" in data
    assert "status" in data["market"]

def test_auth_rejection_missing_header():
    response = client.get("/api/models")
    assert response.status_code == 401

def test_auth_rejection_invalid_passcode():
    response = client.get("/api/models", headers={"Authorization": "Bearer wrong-passcode"})
    assert response.status_code == 401

def test_auth_success_valid_passcode():
    valid_passcode = settings.APP_PASSCODE
    response = client.get("/api/models", headers={"Authorization": f"Bearer {valid_passcode}"})
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert len(data["models"]) >= 1

def test_chat_stream_auth_rejection_missing_header():
    response = client.post("/api/chat/stream", json={"messages": [{"role": "user", "content": "test"}]})
    assert response.status_code == 401

def test_chat_stream_auth_rejection_invalid_passcode():
    response = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "test"}]},
        headers={"Authorization": "Bearer wrong-passcode"}
    )
    assert response.status_code == 401

def test_fail_closed_when_passcode_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "APP_PASSCODE", "")
    response = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "test"}]},
        headers={"Authorization": "Bearer test-pass"}
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Server passcode unconfigured."

