import pytest
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock, AsyncMock
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token
from app.routers.quant_levels_status import _CANDLES_CACHE, CandlestickBar

client = TestClient(app)


# ==============================================================================
# 1. HISTORICAL SPOT ANCHORING & DISTANCE DELTAS TESTS
# ==============================================================================

@patch("app.routers.quant_levels_status._get_session_close")
@patch("app.routers.quant_levels_status.postgres.get_quant_levels")
@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_historical_spot_anchoring(mock_config, mock_sql, mock_get_levels, mock_session_close):
    """
    Verifies that viewing a historical session:
    - Resolves spot price from session close (not live quote)
    - Sets spot_type = 'HISTORICAL_CLOSE' and spot_label = 'SPX Session Close'
    - Calculates distance deltas and immediate support/resistance against session close
    """
    mock_config.return_value = MagicMock()
    historical_date_str = "2026-09-08"
    mock_sql.return_value = pd.DataFrame([{"d": historical_date_str}])
    mock_session_close.return_value = 5482.50

    mock_df = pd.DataFrame([
        {
            "DATETIME": f"{historical_date_str} 14:00:00",
            "TICKER": "SPX",
            "START_LVL_PRICE": 5500.0,
            "END_LVL_PRICE": 5510.0,
            "COMMENTS": "Major Call Wall",
            "BUY_SELL_IND": "SELL",
            "WEB_LINK": "https://tradingedge.club/posts/101"
        },
        {
            "DATETIME": f"{historical_date_str} 14:00:00",
            "TICKER": "SPX",
            "START_LVL_PRICE": 5460.0,
            "END_LVL_PRICE": None,
            "COMMENTS": "Major Put Wall",
            "BUY_SELL_IND": "BUY",
            "WEB_LINK": "https://tradingedge.club/posts/101"
        }
    ])
    mock_get_levels.return_value = mock_df

    resp = client.get(f"/api/quant-levels/data?ticker=SPX&as_of_date={historical_date_str}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ok"
    assert data["ticker"] == "SPX"
    assert data["as_of_date"] == historical_date_str
    assert data["spot_price"] == 5482.50
    assert data["spot_type"] == "HISTORICAL_CLOSE"
    assert data["spot_label"] == "SPX Session Close"

    # Summary checks
    summary = data["summary"]
    assert summary["spot_price"] == 5482.50
    assert summary["spot_type"] == "HISTORICAL_CLOSE"
    assert summary["spot_label"] == "SPX Session Close"
    assert summary["immediate_resistance"] == 5500.0
    assert summary["immediate_support"] == 5460.0
    assert summary["channel_width"] == 40.0
    assert summary["total_levels"] == 2

    # Level checks (level 0: 5500-5510, mid = 5505; level 1: 5460, mid = 5460)
    res_lvl = data["levels"][0]
    sup_lvl = data["levels"][1]

    assert res_lvl["start_price"] == 5500.0
    assert res_lvl["end_price"] == 5510.0
    # mid_p = 5505.0 -> distance_pts = 5505.0 - 5482.50 = 22.50
    assert res_lvl["distance_pts"] == 22.50
    assert res_lvl["distance_pct"] == round((22.50 / 5482.50) * 100, 2)
    assert res_lvl["relative_position"] == "ABOVE_SPOT"
    assert res_lvl["is_immediate_resistance"] is True
    assert res_lvl["is_immediate_support"] is False

    assert sup_lvl["start_price"] == 5460.0
    # mid_p = 5460.0 -> distance_pts = 5460.0 - 5482.50 = -22.50
    assert sup_lvl["distance_pts"] == -22.50
    assert sup_lvl["distance_pct"] == round((-22.50 / 5482.50) * 100, 2)
    assert sup_lvl["relative_position"] == "BELOW_SPOT"
    assert sup_lvl["is_immediate_support"] is True
    assert sup_lvl["is_immediate_resistance"] is False


@patch("app.routers.quant_levels_status.get_batch_quotes")
@patch("app.routers.quant_levels_status.postgres.get_quant_levels")
@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_live_spot_anchoring(mock_config, mock_sql, mock_get_levels, mock_quotes):
    """
    Verifies that viewing today's active session:
    - Fetches live quote from get_batch_quotes
    - Sets spot_type = 'LIVE' and spot_label = 'SPX Live Spot'
    """
    mock_config.return_value = MagicMock()
    today_str = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    mock_sql.return_value = pd.DataFrame([{"d": today_str}])
    mock_quotes.return_value = {
        "SPX": {"ticker": "SPX", "price": 5890.0}
    }
    mock_df = pd.DataFrame([
        {
            "DATETIME": f"{today_str} 10:00:00",
            "TICKER": "SPX",
            "START_LVL_PRICE": 5900.0,
            "END_LVL_PRICE": None,
            "COMMENTS": "Resistance",
            "BUY_SELL_IND": "SELL",
            "WEB_LINK": None
        }
    ])
    mock_get_levels.return_value = mock_df

    resp = client.get(f"/api/quant-levels/data?ticker=SPX&as_of_date={today_str}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ok"
    assert data["spot_type"] == "LIVE"
    assert data["spot_label"] == "SPX Live Spot"
    assert data["spot_price"] == 5890.0
    assert data["summary"]["spot_type"] == "LIVE"
    assert data["summary"]["spot_label"] == "SPX Live Spot"
    assert data["summary"]["spot_price"] == 5890.0


# ==============================================================================
# 2. CANDLES SESSION SUMMARY & CACHING TESTS
# ==============================================================================

@patch("httpx.AsyncClient.get")
def test_candles_session_summary_fields(mock_get):
    """
    Verifies that GET /api/quant-levels/candles correctly aggregates and returns:
    session_open, session_close, session_high, session_low, session_change_pts, session_change_pct
    """
    eastern = ZoneInfo("America/New_York")
    target_dt = datetime(2026, 9, 8, 9, 30, tzinfo=eastern)
    ts = int(target_dt.timestamp())

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "chart": {
            "result": [{
                "timestamp": [ts, ts + 300, ts + 600],
                "indicators": {
                    "quote": [{
                        "open": [5465.20, 5470.00, 5480.00],
                        "high": [5472.00, 5490.10, 5485.00],
                        "low": [5455.00, 5468.00, 5475.00],
                        "close": [5470.00, 5480.00, 5482.50],
                        "volume": [100000, 95000, 89000]
                    }]
                }
            }]
        }
    }
    mock_get.return_value = mock_resp

    _CANDLES_CACHE.clear()

    resp = client.get("/api/quant-levels/candles?ticker=SPX&as_of_date=2026-09-08")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ok"
    assert data["as_of_date"] == "2026-09-08"
    assert len(data["candles"]) == 3

    assert data["session_open"] == 5465.20
    assert data["session_close"] == 5482.50
    assert data["session_high"] == 5490.10
    assert data["session_low"] == 5455.00
    # Change: 5482.50 - 5465.20 = 17.30 pts
    assert data["session_change_pts"] == 17.30
    assert data["session_change_pct"] == round((17.30 / 5465.20) * 100, 2)


@patch("httpx.AsyncClient.get")
def test_candles_session_summary_empty(mock_get):
    """
    Verifies that an empty session returns None for session aggregates.
    """
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

    _CANDLES_CACHE.clear()

    resp = client.get("/api/quant-levels/candles?ticker=SPX&as_of_date=2026-09-06")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "empty"
    assert data["session_open"] is None
    assert data["session_close"] is None
    assert data["session_high"] is None
    assert data["session_low"] is None
    assert data["session_change_pts"] is None
    assert data["session_change_pct"] is None
    assert data["candles"] == []


# ==============================================================================
# 3. EXTRACT-DATE ENDPOINT TESTS
# ==============================================================================

def test_extract_target_date_unauthorized():
    """Missing auth header should return 401."""
    resp = client.post("/api/quant-levels/extract-date?target_date=2026-09-08")
    assert resp.status_code == 401


def test_extract_target_date_invalid_date():
    """Invalid date format should return 400 Bad Request."""
    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/quant-levels/extract-date?target_date=invalid-date", headers=headers)
    assert resp.status_code == 400
    data = resp.json()
    assert "Invalid date format" in data["detail"]


@patch("common_lib.quant_levels.runner.run_target_date_extraction")
def test_extract_target_date_success(mock_runner):
    """Valid target_date runs pipeline and returns 200 with row count."""
    mock_runner.return_value = 14

    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/quant-levels/extract-date?target_date=2026-09-08", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ok"
    assert data["target_date"] == "2026-09-08"
    assert data["rows_upserted"] == 14
    assert "Successfully extracted 14 quant levels for 2026-09-08." in data["message"]
    assert mock_runner.call_count == 1
    assert mock_runner.call_args[0][0] == date(2026, 9, 8)


@patch("common_lib.quant_levels.runner.run_target_date_extraction")
def test_extract_target_date_pipeline_error(mock_runner):
    """Pipeline error returns 500 Internal Server Error."""
    mock_runner.side_effect = RuntimeError("Feed timeout connecting to Mighty Networks")

    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/quant-levels/extract-date?target_date=2026-09-08", headers=headers)
    assert resp.status_code == 500
    data = resp.json()
    assert "Targeted date extraction failed" in data["detail"]


# ==============================================================================
# 4. RUNNER TARGET DATE EXTRACTION UNIT TESTS
# ==============================================================================

@patch("common_lib.quant_levels.load.run")
@patch("common_lib.quant_levels.transform.run")
@patch("common_lib.quant_levels.extract.fetch_posts_for_date")
def test_runner_run_target_date_extraction_success(mock_fetch, mock_transform, mock_load):
    from common_lib.quant_levels.runner import run_target_date_extraction
    mock_config = MagicMock()
    target_d = date(2026, 9, 8)

    mock_fetch.return_value = [{"title": "Quant levels 9/8", "date_posted": "2026-09-08T11:00:00Z"}]
    mock_df = pd.DataFrame([
        {"DATETIME": "2026-09-08", "TICKER": "SPX", "START_LVL_PRICE": 5500.0}
    ])
    mock_transform.return_value = mock_df

    rows = run_target_date_extraction(target_d, mock_config)
    assert rows == 1
    mock_fetch.assert_called_once_with(mock_config, target_d)
    mock_transform.assert_called_once()
    mock_load.assert_called_once_with(mock_config, "upsert", mock_df)


@patch("common_lib.quant_levels.extract.fetch_posts_for_date")
def test_runner_run_target_date_extraction_no_posts(mock_fetch):
    from common_lib.quant_levels.runner import run_target_date_extraction
    mock_config = MagicMock()
    mock_fetch.return_value = []

    rows = run_target_date_extraction(date(2026, 9, 8), mock_config)
    assert rows == 0
