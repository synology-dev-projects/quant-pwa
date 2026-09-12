import pytest
from datetime import datetime, date, time
from unittest.mock import patch, MagicMock
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.routers.quant_levels_status import get_expected_quant_levels_date
from app.core.auth import create_session_token

client = TestClient(app)


# ==============================================================================
# EXPECTED QUANT LEVELS DATE HELPER TESTS
# ==============================================================================

def test_get_expected_quant_levels_date_saturday():
    # Saturday Aug 29, 2026 -> expects Friday Aug 28, 2026
    sat_dt = datetime(2026, 8, 29, 14, 0)
    assert get_expected_quant_levels_date(sat_dt) == date(2026, 8, 28)


def test_get_expected_quant_levels_date_sunday():
    # Sunday Aug 30, 2026 -> expects Friday Aug 28, 2026
    sun_dt = datetime(2026, 8, 30, 10, 0)
    assert get_expected_quant_levels_date(sun_dt) == date(2026, 8, 28)


def test_get_expected_quant_levels_date_monday():
    # Monday Aug 31, 2026 before 6:30 AM -> expects Friday Aug 28, 2026
    mon_early = datetime(2026, 8, 31, 6, 15)
    assert get_expected_quant_levels_date(mon_early) == date(2026, 8, 28)

    # Monday Aug 31, 2026 at or after 6:30 AM -> expects Monday Aug 31, 2026 (today)
    mon_after = datetime(2026, 8, 31, 6, 30)
    assert get_expected_quant_levels_date(mon_after) == date(2026, 8, 31)
    mon_afternoon = datetime(2026, 8, 31, 15, 0)
    assert get_expected_quant_levels_date(mon_afternoon) == date(2026, 8, 31)


def test_get_expected_quant_levels_date_tuesday():
    # Tuesday Sep 1, 2026 before 6:30 AM -> expects Monday Aug 31, 2026 (yesterday)
    tue_early = datetime(2026, 9, 1, 5, 45)
    assert get_expected_quant_levels_date(tue_early) == date(2026, 8, 31)

    # Tuesday Sep 1, 2026 at or after 6:30 AM -> expects Tuesday Sep 1, 2026 (today)
    tue_after = datetime(2026, 9, 1, 6, 30)
    assert get_expected_quant_levels_date(tue_after) == date(2026, 9, 1)


def test_get_expected_quant_levels_date_friday():
    # Friday Sep 4, 2026 before 6:30 AM -> expects Thursday Sep 3, 2026 (yesterday)
    fri_early = datetime(2026, 9, 4, 6, 29)
    assert get_expected_quant_levels_date(fri_early) == date(2026, 9, 3)

    # Friday Sep 4, 2026 at 6:30 AM -> expects Friday Sep 4, 2026 (today)
    fri_after = datetime(2026, 9, 4, 6, 30)
    assert get_expected_quant_levels_date(fri_after) == date(2026, 9, 4)


# ==============================================================================
# GET /api/quant-levels/status ENDPOINT TESTS
# ==============================================================================

@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_get_quant_levels_status_synced(mock_config, mock_sql):
    mock_config.return_value = MagicMock()
    expected_day = get_expected_quant_levels_date().strftime("%Y-%m-%d")
    mock_df = pd.DataFrame([{
        "max_date": expected_day,
        "total_count": 520,
        "expected_day_count": 18
    }])
    mock_sql.return_value = mock_df

    response = client.get("/api/quant-levels/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "synced"
    assert data["is_fresh"] is True
    assert data["latest_record_date"] == expected_day
    assert data["total_records"] == 520
    assert data["expected_day_records"] == 18
    assert "up to date" in data["message"]


@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_get_quant_levels_status_stale(mock_config, mock_sql):
    mock_config.return_value = MagicMock()
    mock_df = pd.DataFrame([{
        "max_date": "2026-08-20",
        "total_count": 480,
        "expected_day_count": 0
    }])
    mock_sql.return_value = mock_df

    response = client.get("/api/quant-levels/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stale"
    assert data["is_fresh"] is False
    assert data["latest_record_date"] == "2026-08-20"
    assert data["expected_day_records"] == 0
    assert "missing" in data["message"].lower()


@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_get_quant_levels_status_empty_db(mock_config, mock_sql):
    mock_config.return_value = MagicMock()
    mock_sql.return_value = pd.DataFrame()

    response = client.get("/api/quant-levels/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stale"
    assert data["is_fresh"] is False
    assert data["total_records"] == 0
    assert data["latest_record_date"] is None


@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_get_quant_levels_status_db_error(mock_config, mock_sql):
    mock_config.return_value = MagicMock()
    mock_sql.side_effect = Exception("DB connection timeout")

    response = client.get("/api/quant-levels/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert data["is_fresh"] is False
    assert "Database query error" in data["message"]


# ==============================================================================
# POST /api/quant-levels/sync ENDPOINT TESTS
# ==============================================================================

def test_trigger_quant_levels_sync_unauthorized():
    response = client.post("/api/quant-levels/sync")
    assert response.status_code == 401


@patch("common_lib.quant_levels.runner.run_daily_incremental")
def test_trigger_quant_levels_sync_authorized(mock_run):
    mock_run.return_value = 18

    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/quant-levels/sync", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["rows_upserted"] == 18
    assert "Ingested 18 records" in data["message"]


@patch("common_lib.quant_levels.runner.run_daily_incremental")
def test_trigger_quant_levels_sync_pipeline_error(mock_run):
    mock_run.side_effect = RuntimeError("Trading Edge scrape failed")

    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/quant-levels/sync", headers=headers)
    assert response.status_code == 500
    data = response.json()
    assert "Pipeline execution failed" in data["detail"]


# ==============================================================================
# COMMON_LIB QUANT LEVELS RUNNER TESTS
# ==============================================================================

@patch("common_lib.quant_levels.load.run")
@patch("common_lib.quant_levels.load._quant_lvl_df_to_string")
@patch("common_lib.quant_levels.runner.nfty.send_ntfy_notification")
@patch("common_lib.quant_levels.transform.run")
@patch("common_lib.quant_levels.extract.run")
@patch("common_lib.quant_levels.load._get_latest_recorded_date")
def test_run_daily_incremental_success(
    mock_get_cutoff,
    mock_extract,
    mock_transform,
    mock_ntfy,
    mock_to_str,
    mock_load_run
):
    from common_lib.quant_levels.runner import run_daily_incremental
    mock_config = MagicMock()
    mock_get_cutoff.return_value = datetime(2026, 8, 28, 0, 0)
    mock_extract.return_value = [{"title": "Quant levels for 8/29", "date_posted": "2026-08-29T10:00:00Z"}]
    mock_df = pd.DataFrame([
        {"DATETIME": "2026-08-29", "TICKER": "SPX", "START_LVL_PRICE": 5600.0, "END_LVL_PRICE": 5620.0}
    ])
    mock_transform.return_value = mock_df
    mock_to_str.return_value = "QUANT LVL FOR DATE: 2026-08-29\n5600.0 5620.0"

    rows = run_daily_incremental(mock_config)
    assert rows == 1
    mock_extract.assert_called_once_with(mock_config, cutoff_date=datetime(2026, 8, 28, 0, 0))
    mock_transform.assert_called_once()
    mock_ntfy.assert_called_once()
    mock_load_run.assert_called_once_with(mock_config, "upsert", mock_df)


@patch("common_lib.quant_levels.extract.run")
@patch("common_lib.quant_levels.load._get_latest_recorded_date")
def test_run_daily_incremental_no_new_posts(mock_get_cutoff, mock_extract):
    from common_lib.quant_levels.runner import run_daily_incremental
    mock_config = MagicMock()
    mock_get_cutoff.return_value = datetime(2026, 8, 28, 0, 0)
    mock_extract.return_value = []

    rows = run_daily_incremental(mock_config)
    assert rows == 0


# ==============================================================================
# SPX QUANT LEVELS DATA COMMENT PURGE TESTS
# ==============================================================================

@patch("app.routers.quant_levels_status.postgres.get_quant_levels")
@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_get_quant_levels_data_sanitizes_nan_comments(mock_config, mock_sql, mock_get_levels):
    mock_config.return_value = MagicMock()
    mock_sql.return_value = pd.DataFrame([{"d": "2026-09-11"}])
    mock_get_levels.return_value = pd.DataFrame([
        {
            "DATETIME": "2026-09-11",
            "TICKER": "SPX",
            "START_LVL_PRICE": 5600.0,
            "END_LVL_PRICE": None,
            "BUY_SELL_IND": "BUY",
            "COMMENTS": float("nan"),
            "WEB_LINK": "nan"
        },
        {
            "DATETIME": "2026-09-11",
            "TICKER": "SPX",
            "START_LVL_PRICE": 5700.0,
            "END_LVL_PRICE": None,
            "BUY_SELL_IND": "SELL",
            "COMMENTS": "Major supply zone",
            "WEB_LINK": "https://example.com"
        },
        {
            "DATETIME": "2026-09-11",
            "TICKER": "SPX",
            "START_LVL_PRICE": 5500.0,
            "END_LVL_PRICE": None,
            "BUY_SELL_IND": "BUY",
            "COMMENTS": "NaN",
            "WEB_LINK": None
        }
    ])

    response = client.get("/api/quant-levels/data?ticker=SPX&as_of_date=2026-09-11")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    levels = data["levels"]
    assert len(levels) == 3

    # Sorted descending by START_LVL_PRICE:
    # idx 0: 5700 (Major supply zone)
    # idx 1: 5600 (float nan -> None)
    # idx 2: 5500 ("NaN" -> None)
    assert levels[0]["start_price"] == 5700.0
    assert levels[0]["comments"] == "Major supply zone"
    assert levels[0]["web_link"] == "https://example.com"

    assert levels[1]["start_price"] == 5600.0
    assert levels[1]["comments"] is None
    assert levels[1]["web_link"] is None

    assert levels[2]["start_price"] == 5500.0
    assert levels[2]["comments"] is None


# ==============================================================================
# SPX CANDLESTICK INTRADAY 5M ENDPOINT TESTS
# ==============================================================================

@patch("httpx.AsyncClient.get")
def test_get_quant_levels_candles_success(mock_get):
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo("America/New_York")
    ts = int(datetime(2026, 9, 11, 9, 30, tzinfo=eastern).timestamp())

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "chart": {
            "result": [{
                "timestamp": [ts, ts + 300],
                "indicators": {
                    "quote": [{
                        "open": [5600.0, 5605.0],
                        "high": [5610.0, 5615.0],
                        "low": [5595.0, 5600.0],
                        "close": [5605.0, 5612.0],
                        "volume": [12000, 15000]
                    }]
                }
            }]
        }
    }
    mock_get.return_value = mock_resp

    from app.routers.quant_levels_status import _CANDLES_CACHE
    _CANDLES_CACHE.clear()

    response = client.get("/api/quant-levels/candles?ticker=SPX&as_of_date=2026-09-11")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["ticker"] == "SPX"
    assert data["as_of_date"] == "2026-09-11"
    assert len(data["candles"]) == 2
    assert data["candles"][0]["open"] == 5600.0
    assert data["candles"][0]["close"] == 5605.0
    assert data["candles"][0]["datetime"] == "09:30"


@patch("httpx.AsyncClient.get")
def test_get_quant_levels_candles_empty(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "chart": {
            "result": [{
                "timestamp": [],
                "indicators": {"quote": [{"open": [], "high": [], "low": [], "close": []}]}
            }]
        }
    }
    mock_get.return_value = mock_resp

    from app.routers.quant_levels_status import _CANDLES_CACHE
    _CANDLES_CACHE.clear()

    response = client.get("/api/quant-levels/candles?ticker=SPX&as_of_date=2026-09-13")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "empty"
    assert len(data["candles"]) == 0
    assert "No intraday session candles available" in data["message"]


@patch("httpx.AsyncClient.get")
def test_get_quant_levels_candles_error(mock_get):
    mock_get.side_effect = Exception("Yahoo Finance connection timeout")

    from app.routers.quant_levels_status import _CANDLES_CACHE
    _CANDLES_CACHE.clear()

    response = client.get("/api/quant-levels/candles?ticker=SPX&as_of_date=2026-09-14")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert data["candles"] == []
    assert "Failed to retrieve SPX intraday candles" in data["message"]

