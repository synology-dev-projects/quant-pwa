"""
Unit Tests for Gateway Pipelines & DAG Dependency Management Router.
"""

import pytest
from datetime import date
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    token, _ = create_session_token()
    return {"Authorization": f"Bearer {token}"}


def test_get_pipeline_dag(client):
    response = client.get("/api/pipelines/dag")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "topological_order" in data
    assert "batches" in data
    assert "dag" in data

    order = data["topological_order"]
    assert "unusual_option_flow" in order
    assert "gexdex_snapshot" in order
    assert "market_confluence" in order

    # Verify flow precedes snapshot and confluence
    assert order.index("unusual_option_flow") < order.index("gexdex_snapshot")
    assert order.index("gexdex_snapshot") < order.index("market_confluence")


def test_get_pipeline_status_endpoint(client):
    with patch("app.routers.pipelines_router.get_all_pipeline_statuses") as mock_statuses:
        mock_statuses.return_value = {
            "unusual_option_flow": {
                "pipeline_name": "unusual_option_flow",
                "session_date": "2026-09-08",
                "status": "SUCCESS",
                "rows_affected": 142,
                "started_at": "2026-09-08T16:35:00Z",
                "completed_at": "2026-09-08T16:37:12Z",
                "error_message": None,
            }
        }
        with patch("app.routers.pipelines_router.get_market_calendar_context") as mock_cal:
            mock_cal.return_value = (True, date(2026, 9, 8), date(2026, 9, 8))

            response = client.get("/api/pipelines/status?date=2026-09-08")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["session_date"] == "2026-09-08"
            assert "pipelines" in data
            assert data["pipelines"]["unusual_option_flow"]["status"] == "SUCCESS"
            assert data["pipelines"]["gexdex_snapshot"]["status"] == "NOT_STARTED"
            assert data["all_success"] is False


def test_trigger_pipeline_run_unauthorized(client):
    response = client.post("/api/pipelines/run", json={"pipeline_name": "gexdex_snapshot"})
    assert response.status_code in [401, 403]


def test_trigger_pipeline_run_dry_run_authorized(client, auth_headers):
    with patch("app.routers.pipelines_router.run_dag_cycle") as mock_cycle:
        mock_cycle.return_value = {
            "dry_run": True,
            "session_date": "2026-09-08",
            "topological_sequence": ["unusual_option_flow", "gexdex_snapshot"],
            "plan": [
                {"pipeline_name": "unusual_option_flow", "planned_action": "EXECUTE"},
                {"pipeline_name": "gexdex_snapshot", "planned_action": "BLOCKED"},
            ],
        }

        response = client.post(
            "/api/pipelines/run",
            json={"session_date": "2026-09-08", "dry_run": True},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["execution"]["dry_run"] is True
        assert len(data["execution"]["plan"]) == 2
