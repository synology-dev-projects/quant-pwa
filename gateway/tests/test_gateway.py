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
