"""
Tests for Economic Events Gateway Endpoints.
Verifies GET /api/economic-events filtering, response formatting, and POST /api/economic-events/sync lifecycle.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_economic_events_empty():
    """Verifies that an empty database table returns HTTP 200 with empty list."""
    with patch("common_lib.connectors.postgres.get_economic_events", return_value=pd.DataFrame()):
        response = client.get("/api/economic-events")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["count"] == 0
        assert data["events"] == []


def test_list_economic_events_with_data():
    """Verifies event mapping, field extraction, and status detection."""
    mock_df = pd.DataFrame([
        {
            "EVENT_ID": "e123",
            "EVENT_TIMESTAMP": pd.to_datetime("2026-09-23T12:30:00Z"),
            "COUNTRY": "USD",
            "TITLE": "Core CPI m/m",
            "IMPACT_TIER": "High",
            "FORECAST": "0.3%",
            "PREVIOUS": "0.2%",
            "ACTUAL": "0.3%",
            "SYNTHETIC_SUMMARY": "Macroeconomic Event: [USD] Core CPI m/m",
            "RAW_PAYLOAD": "{}"
        },
        {
            "EVENT_ID": "e124",
            "EVENT_TIMESTAMP": pd.to_datetime("2026-09-24T12:30:00Z"),
            "COUNTRY": "USD",
            "TITLE": "Initial Jobless Claims",
            "IMPACT_TIER": "High",
            "FORECAST": "220K",
            "PREVIOUS": "219K",
            "ACTUAL": None,
            "SYNTHETIC_SUMMARY": "Macroeconomic Event: [USD] Initial Jobless Claims",
            "RAW_PAYLOAD": "{}"
        }
    ])

    with patch("common_lib.connectors.postgres.get_economic_events", return_value=mock_df) as mock_get:
        response = client.get("/api/economic-events?country=USD&min_impact=High&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["count"] == 2

        # First event (released)
        ev1 = data["events"][0]
        assert ev1["event_id"] == "e123"
        assert ev1["country"] == "USD"
        assert ev1["actual"] == "0.3%"
        assert ev1["status"] == "RELEASED"

        # Second event (upcoming)
        ev2 = data["events"][1]
        assert ev2["event_id"] == "e124"
        assert ev2["actual"] is None
        assert ev2["status"] == "UPCOMING"

        # Verify arguments passed to connector
        mock_get.assert_called_once()
        kwargs = mock_get.call_args[1]
        assert kwargs["country"] == ["USD"]
        assert kwargs["min_impact"] == "High"
        assert kwargs["limit"] == 10


def test_sync_economic_events_cooldown_and_force():
    """Verifies sync invocation, rate limit throttling, and force override."""
    mock_sync_result = {
        "status": "success",
        "duration_seconds": 0.45,
        "raw_extracted": 50,
        "records_transformed": 45,
        "records_loaded": 45
    }

    with patch("app.routers.economic_events._run_sync", return_value=mock_sync_result) as mock_run:
        # 1. First sync with force=True succeeds
        res1 = client.post("/api/economic-events/sync?force=true")
        assert res1.status_code == 200
        assert res1.json()["status"] == "success"
        assert res1.json()["result"]["records_loaded"] == 45

        # 2. Immediate second sync without force gets throttled
        res2 = client.post("/api/economic-events/sync")
        assert res2.status_code == 200
        assert res2.json()["status"] == "throttled"
        assert "cooldown active" in res2.json()["message"]

        # 3. Third sync with force=True bypasses throttle
        res3 = client.post("/api/economic-events/sync?force=true")
        assert res3.status_code == 200
        assert res3.json()["status"] == "success"
