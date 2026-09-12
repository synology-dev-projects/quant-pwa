import pytest
from datetime import datetime, date
from unittest.mock import patch, MagicMock
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ==============================================================================
# DATES ENDPOINT TESTS
# ==============================================================================

@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_get_quant_levels_dates_empty(mock_config, mock_sql):
    mock_sql.return_value = pd.DataFrame()
    resp = client.get("/api/quant-levels/dates?ticker=SPX")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_get_quant_levels_dates_success(mock_config, mock_sql):
    mock_sql.return_value = pd.DataFrame([{"d": "2026-09-10"}, {"d": "2026-09-09"}])
    resp = client.get("/api/quant-levels/dates?ticker=SPX")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0] == "2026-09-10"
    assert data[1] == "2026-09-09"


# ==============================================================================
# DATA ENDPOINT TESTS
# ==============================================================================

@patch("app.routers.quant_levels_status.postgres.get_quant_levels")
@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_get_quant_levels_data_empty(mock_config, mock_sql, mock_get_levels):
    mock_sql.return_value = pd.DataFrame()
    mock_get_levels.return_value = pd.DataFrame()

    resp = client.get("/api/quant-levels/data")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "empty"
    assert data["ticker"] == "SPX"
    assert data["levels"] == []
    assert data["summary"]["total_levels"] == 0


@patch("app.routers.quant_levels_status.get_batch_quotes")
@patch("app.routers.quant_levels_status.postgres.get_quant_levels")
@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
def test_get_quant_levels_data_structured_levels(mock_config, mock_sql, mock_get_levels, mock_quotes):
    today_str = datetime.now().strftime("%Y-%m-%d")
    mock_sql.return_value = pd.DataFrame([{"d": today_str}])
    mock_quotes.return_value = {
        "^SPX": {"ticker": "^SPX", "price": 5820.0}
    }

    mock_df = pd.DataFrame([
        {
            "DATETIME": f"{today_str} 14:00:00",
            "TICKER": "SPX",
            "START_LVL_PRICE": 5850.0,
            "END_LVL_PRICE": 5860.0,
            "COMMENTS": "Major Resistance",
            "BUY_SELL_IND": "SELL",
            "WEB_LINK": "https://example.com/post/1"
        },
        {
            "DATETIME": f"{today_str} 14:00:00",
            "TICKER": "SPX",
            "START_LVL_PRICE": 5800.0,
            "END_LVL_PRICE": None,
            "COMMENTS": "Session Pivot",
            "BUY_SELL_IND": None,
            "WEB_LINK": "https://example.com/post/1"
        },
        {
            "DATETIME": f"{today_str} 14:00:00",
            "TICKER": "SPX",
            "START_LVL_PRICE": 5750.0,
            "END_LVL_PRICE": 5760.0,
            "COMMENTS": "Major Support",
            "BUY_SELL_IND": "BUY",
            "WEB_LINK": "https://example.com/post/1"
        },
    ])
    mock_get_levels.return_value = mock_df

    resp = client.get(f"/api/quant-levels/data?ticker=SPX&as_of_date={today_str}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ok"
    assert data["ticker"] == "SPX"
    assert data["spot_price"] == 5820.0
    assert len(data["levels"]) == 3

    # Sorted descending by START_LVL_PRICE
    lvl_top = data["levels"][0]
    lvl_mid = data["levels"][1]
    lvl_bot = data["levels"][2]

    assert lvl_top["start_price"] == 5850.0
    assert lvl_top["type"] == "SELL"
    assert lvl_top["relative_position"] == "ABOVE_SPOT"
    assert lvl_top["is_immediate_resistance"] is True
    assert lvl_top["is_immediate_support"] is False

    assert lvl_mid["start_price"] == 5800.0
    assert lvl_mid["type"] == "PIVOT"
    assert lvl_mid["relative_position"] == "BELOW_SPOT"
    assert lvl_mid["is_immediate_support"] is True
    assert lvl_mid["is_immediate_resistance"] is False

    assert lvl_bot["start_price"] == 5750.0
    assert lvl_bot["type"] == "BUY"
    assert lvl_bot["relative_position"] == "BELOW_SPOT"

    # Summary metrics
    assert data["summary"]["immediate_resistance"] == 5850.0
    assert data["summary"]["immediate_support"] == 5800.0
    assert data["summary"]["channel_width"] == 50.0
    assert data["summary"]["buy_levels_count"] == 1
    assert data["summary"]["sell_levels_count"] == 1
    assert data["summary"]["total_levels"] == 3
