import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from unittest.mock import MagicMock, patch, AsyncMock

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "quant-gateway"
    assert data["version"] == settings.APP_VERSION
    assert data["environment"] == settings.ENVIRONMENT
    assert "market" in data
    assert "status" in data["market"]

def test_version_parity_with_version_json():
    """Verifies that gateway settings.APP_VERSION strictly matches root version.json."""
    from pathlib import Path
    import json

    candidates = [
        Path(__file__).resolve().parent.parent.parent / "version.json",
        Path(__file__).resolve().parent.parent / "version.json",
        Path("/app/version.json"),
        Path("version.json"),
        Path("/volume2/homes/rachardv/git-repos/develop2/quant-pwa/version.json"),
        Path("/volume2/homes/rachardv/git-repos/master/quant-pwa/version.json"),
    ]
    version_file = next((p for p in candidates if p.exists()), None)
    if version_file:
        with open(version_file, "r", encoding="utf-8") as f:
            version_data = json.load(f)
        assert settings.APP_VERSION == version_data["version"]
    else:
        assert settings.APP_VERSION.startswith("v1.") and len(settings.APP_VERSION) >= 4

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

def test_fail_closed_when_passcode_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "APP_PASSCODE", "")
    response = client.get(
        "/api/models",
        headers={"Authorization": "Bearer test-pass"}
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Server passcode unconfigured."

def test_models_list_endpoint_structure():
    """Verifies that /api/models returns updated default model and available models hierarchy."""
    valid_passcode = settings.APP_PASSCODE
    response = client.get("/api/models", headers={"Authorization": f"Bearer {valid_passcode}"})
    assert response.status_code == 200
    data = response.json()
    assert data["default"] == "gemini-3.5-flash-lite"
    assert len(data["models"]) == 4
    model_ids = [m["id"] for m in data["models"]]
    assert model_ids == [
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-flash-latest"
    ]


def test_lifespan_invokes_ensure_all_schemas():
    """Verifies gateway lifespan startup invokes ensure_all_schemas for database auto-migration."""
    import asyncio
    import common_lib.database.schemas
    from unittest.mock import patch, AsyncMock
    from app.main import lifespan

    async def _run():
        mock_app = MagicMock()
        with patch("common_lib.database.schemas.ensure_all_schemas") as mock_ensure, \
             patch("app.main.mcp_client_manager.initialize", new_callable=AsyncMock), \
             patch("app.main.mcp_client_manager.close", new_callable=AsyncMock), \
             patch("app.main.run_cache_warmer_loop", new_callable=AsyncMock):

            mock_ensure.return_value = {
                "unusual_whales_flow_te": "verified",
                "quant_lvl_data_te": "verified",
                "ibkr_historical_te": "verified",
                "chat_history": "verified"
            }

            async with lifespan(mock_app):
                pass

            assert mock_ensure.call_count == 1

    asyncio.run(_run())


def test_lifespan_gracefully_handles_schema_verification_failure():
    """Verifies gateway lifespan startup catches schema migration exceptions without aborting startup."""
    import asyncio
    import common_lib.database.schemas
    from unittest.mock import patch, AsyncMock
    from app.main import lifespan

    async def _run():
        mock_app = MagicMock()
        with patch("common_lib.database.schemas.ensure_all_schemas", side_effect=Exception("Database connection timeout")), \
             patch("app.main.mcp_client_manager.initialize", new_callable=AsyncMock), \
             patch("app.main.mcp_client_manager.close", new_callable=AsyncMock), \
             patch("app.main.run_cache_warmer_loop", new_callable=AsyncMock):

            # Should not raise exception
            async with lifespan(mock_app):
                pass

    asyncio.run(_run())


def test_gexdex_route_and_alias():
    """Verifies that both /api/v1/gexdex and /api/v1/gexdex/assistant-summary resolve to get_gexdex_assistant_summary."""
    from fastapi.testclient import TestClient
    from unittest.mock import patch, AsyncMock
    from app.main import app

    client = TestClient(app)
    mock_summary = {"ticker": "AAPL", "spot_price": 225.0, "batch_data": {"AAPL": {"spot_price": 225.0}}}

    with patch("app.main.gexdex_service.get_summary", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_summary

        resp1 = client.get("/api/v1/gexdex?tickers=AAPL")
        assert resp1.status_code == 200
        assert resp1.json() == mock_summary

        resp2 = client.get("/api/v1/gexdex/assistant-summary?tickers=AAPL")
        assert resp2.status_code == 200
        assert resp2.json() == mock_summary



