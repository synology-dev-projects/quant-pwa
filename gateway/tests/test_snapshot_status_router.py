import pytest
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.routers.snapshot_status import get_market_calendar_context
from app.core.auth import create_session_token

client = TestClient(app)


# ==============================================================================
# 1. MARKET CALENDAR CONTEXT HELPER TESTS
# ==============================================================================

def test_market_calendar_context_tuesday_after_labor_day():
    # Tuesday Sep 8, 2026 (market day) -> last market day is Friday Sep 4 (skips Labor Day Sep 7)
    dt = datetime(2026, 9, 8, 14, 0)
    is_market_day, today_d, last_d = get_market_calendar_context(dt)
    assert is_market_day is True
    assert today_d == date(2026, 9, 8)
    assert last_d == date(2026, 9, 4)


def test_market_calendar_context_labor_day():
    # Monday Sep 7, 2026 (Labor Day holiday) -> is_market_day is False, last market day is Friday Sep 4
    dt = datetime(2026, 9, 7, 10, 0)
    is_market_day, today_d, last_d = get_market_calendar_context(dt)
    assert is_market_day is False
    assert today_d == date(2026, 9, 7)
    assert last_d == date(2026, 9, 4)


def test_market_calendar_context_weekend():
    # Saturday Sep 5, 2026 -> is_market_day is False, last market day is Friday Sep 4
    dt = datetime(2026, 9, 5, 12, 0)
    is_market_day, today_d, last_d = get_market_calendar_context(dt)
    assert is_market_day is False
    assert today_d == date(2026, 9, 5)
    assert last_d == date(2026, 9, 4)


# ==============================================================================
# 2. GET /api/snapshot/status ENDPOINT TESTS
# ==============================================================================

def test_snapshot_status_synced_with_last_market_day():
    # On Tuesday Sep 8, having snapshot from Friday Sep 4 is considered synced!
    ref_dt = datetime(2026, 9, 8, 14, 0)
    tbl_df = pd.DataFrame([{"tbl_exists": True}])
    summary_df = pd.DataFrame([{
        "max_date": "2026-09-04",
        "total_count": 16,
        "latest_day_count": 16
    }])

    with patch("app.routers.snapshot_status.get_market_calendar_context", return_value=(True, date(2026, 9, 8), date(2026, 9, 4))), \
         patch("common_lib.connectors.postgres.sql", side_effect=[tbl_df, summary_df]):

        res = client.get("/api/snapshot/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "synced"
        assert data["is_fresh"] is True
        assert data["latest_snapshot_date"] == "2026-09-04"
        assert data["total_records"] == 16
        assert "up to date" in data["message"]


def test_snapshot_status_synced_with_today():
    # On Tuesday Sep 8, having snapshot from today 2026-09-08 is also synced!
    tbl_df = pd.DataFrame([{"tbl_exists": True}])
    summary_df = pd.DataFrame([{
        "max_date": "2026-09-08",
        "total_count": 32,
        "latest_day_count": 16
    }])

    with patch("app.routers.snapshot_status.get_market_calendar_context", return_value=(True, date(2026, 9, 8), date(2026, 9, 4))), \
         patch("common_lib.connectors.postgres.sql", side_effect=[tbl_df, summary_df]):

        res = client.get("/api/snapshot/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "synced"
        assert data["is_fresh"] is True
        assert data["latest_snapshot_date"] == "2026-09-08"


def test_snapshot_status_stale_older_than_last_market_day():
    # On Tuesday Sep 8, snapshot is from Sep 2 -> Stale!
    tbl_df = pd.DataFrame([{"tbl_exists": True}])
    summary_df = pd.DataFrame([{
        "max_date": "2026-09-02",
        "total_count": 16,
        "latest_day_count": 16
    }])

    with patch("app.routers.snapshot_status.get_market_calendar_context", return_value=(True, date(2026, 9, 8), date(2026, 9, 4))), \
         patch("common_lib.connectors.postgres.sql", side_effect=[tbl_df, summary_df]):

        res = client.get("/api/snapshot/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "stale"
        assert data["is_fresh"] is False
        assert data["latest_snapshot_date"] == "2026-09-02"
        assert "missing latest session" in data["message"].lower()


def test_snapshot_status_non_market_day():
    # On Sunday Sep 6 (weekend), snapshot from Friday Sep 4 -> Synced!
    tbl_df = pd.DataFrame([{"tbl_exists": True}])
    summary_df = pd.DataFrame([{
        "max_date": "2026-09-04",
        "total_count": 16,
        "latest_day_count": 16
    }])

    with patch("app.routers.snapshot_status.get_market_calendar_context", return_value=(False, date(2026, 9, 6), date(2026, 9, 4))), \
         patch("common_lib.connectors.postgres.sql", side_effect=[tbl_df, summary_df]):

        res = client.get("/api/snapshot/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "synced"
        assert data["is_fresh"] is True


def test_snapshot_status_table_missing():
    tbl_df = pd.DataFrame([{"tbl_exists": False}])

    with patch("app.routers.snapshot_status.get_market_calendar_context", return_value=(True, date(2026, 9, 8), date(2026, 9, 4))), \
         patch("common_lib.connectors.postgres.sql", return_value=tbl_df):

        res = client.get("/api/snapshot/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "stale"
        assert data["is_fresh"] is False
        assert "not yet been initialized" in data["message"]


# ==============================================================================
# 3. POST /api/snapshot/sync ENDPOINT TESTS
# ==============================================================================

def test_trigger_snapshot_sync_unauthorized():
    # No auth header -> 401
    res = client.post("/api/snapshot/sync")
    assert res.status_code == 401


def test_trigger_snapshot_sync_success():
    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.engine.snapshot_pipeline.run_snapshot_pipeline", return_value=(16, date(2026, 9, 8), "Committed 16 snapshot rows")):
        res = client.post("/api/snapshot/sync", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["rows_upserted"] == 16
        assert data["snapshot_date"] == "2026-09-08"
        assert "Committed 16 snapshot rows" in data["message"]