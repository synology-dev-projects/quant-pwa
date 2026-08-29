import pytest
from datetime import datetime, date, time
from unittest.mock import patch, MagicMock
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.routers.flow_status import get_last_market_day
from app.core.auth import create_session_token

client = TestClient(app)


def test_get_last_market_day_saturday():
    # Saturday Aug 29, 2026 -> expects Friday Aug 28, 2026
    sat_dt = datetime(2026, 8, 29, 14, 0)
    assert get_last_market_day(sat_dt) == date(2026, 8, 28)


def test_get_last_market_day_sunday():
    # Sunday Aug 30, 2026 -> expects Friday Aug 28, 2026
    sun_dt = datetime(2026, 8, 30, 10, 0)
    assert get_last_market_day(sun_dt) == date(2026, 8, 28)


def test_get_last_market_day_monday():
    # Monday Aug 31, 2026 -> expects Friday Aug 28, 2026
    mon_morning = datetime(2026, 8, 31, 6, 0)
    assert get_last_market_day(mon_morning) == date(2026, 8, 28)
    mon_afternoon = datetime(2026, 8, 31, 15, 0)
    assert get_last_market_day(mon_afternoon) == date(2026, 8, 28)


def test_get_last_market_day_tuesday():
    # Tuesday Sep 1, 2026 before 6:30 AM -> expects Friday Aug 28, 2026
    tue_early = datetime(2026, 9, 1, 5, 0)
    assert get_last_market_day(tue_early) == date(2026, 8, 28)
    # Tuesday Sep 1, 2026 after 6:30 AM -> expects Monday Aug 31, 2026
    tue_after = datetime(2026, 9, 1, 7, 0)
    assert get_last_market_day(tue_after) == date(2026, 8, 31)


def test_get_last_market_day_wednesday():
    # Wednesday Sep 2, 2026 after 6:30 AM -> expects Tuesday Sep 1, 2026
    wed_after = datetime(2026, 9, 2, 8, 0)
    assert get_last_market_day(wed_after) == date(2026, 9, 1)


@patch("app.routers.flow_status.postgres.sql")
@patch("app.routers.flow_status.load_config")
def test_get_flow_status_synced(mock_config, mock_sql):
    mock_config.return_value = MagicMock()
    # Simulate DB returning trade_date >= expected market day
    expected_day = get_last_market_day().strftime("%Y-%m-%d")
    mock_df = pd.DataFrame([{
        "max_date": expected_day,
        "total_count": 2427,
        "expected_day_count": 51
    }])
    mock_sql.return_value = mock_df

    response = client.get("/api/flow/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "synced"
    assert data["is_fresh"] is True
    assert data["latest_trade_date"] == expected_day
    assert data["total_records"] == 2427
    assert data["last_session_records"] == 51


@patch("app.routers.flow_status.postgres.sql")
@patch("app.routers.flow_status.load_config")
def test_get_flow_status_stale(mock_config, mock_sql):
    mock_config.return_value = MagicMock()
    # Simulate DB returning older trade date (e.g. 2026-08-20)
    mock_df = pd.DataFrame([{
        "max_date": "2026-08-20",
        "total_count": 2000,
        "expected_day_count": 0
    }])
    mock_sql.return_value = mock_df

    response = client.get("/api/flow/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stale"
    assert data["is_fresh"] is False
    assert data["latest_trade_date"] == "2026-08-20"


def test_trigger_flow_sync_unauthorized():
    response = client.post("/api/flow/sync")
    assert response.status_code == 401


@patch("app.routers.flow_status.subprocess.run")
def test_trigger_flow_sync_authorized(mock_subproc):
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "Sync success"
    mock_subproc.return_value = mock_proc

    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/flow/sync", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
