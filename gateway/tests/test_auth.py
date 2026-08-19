import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.core.auth import (
    create_session_token,
    verify_session_token,
    validate_master_password
)

client = TestClient(app)

def test_validate_master_password():
    assert validate_master_password(settings.APP_PASSCODE) is True
    assert validate_master_password("wrong-password-xyz") is False

def test_session_token_lifecycle():
    # Generate token valid for 6 hours
    token, expires_at = create_session_token(expires_in_hours=6)
    assert token is not None
    assert expires_at > int(time.time())

    # Verify token
    payload = verify_session_token(token)
    assert payload is not None
    assert payload["sub"] == "quant-user"
    assert payload["exp"] == expires_at

def test_session_token_expired():
    # Generate an expired token (expires -1 hour ago)
    token, expires_at = create_session_token(expires_in_hours=-1)
    payload = verify_session_token(token)
    assert payload is None

def test_session_token_tampered():
    token, _ = create_session_token(expires_in_hours=6)
    parts = token.split('.')
    tampered_token = f"{parts[0]}.{parts[1]}.invalidsignature123"
    assert verify_session_token(tampered_token) is None

def test_auth_endpoints_flow():
    # 1. Check status
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json()["session_expiry_hours"] == 6

    # 2. Login with wrong password
    res = client.post("/api/auth/login", json={"password": "bad-password"})
    assert res.status_code == 401

    # 3. Login with correct master password
    res = client.post("/api/auth/login", json={"password": settings.APP_PASSCODE})
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["expires_in_hours"] == 6
    session_token = data["token"]

    # 4. Verify session endpoint with token
    res = client.get("/api/auth/verify", headers={"Authorization": f"Bearer {session_token}"})
    assert res.status_code == 200
    assert res.json()["valid"] is True

    # 5. Access models with session token
    res = client.get("/api/models", headers={"Authorization": f"Bearer {session_token}"})
    assert res.status_code == 200
    assert "models" in res.json()
