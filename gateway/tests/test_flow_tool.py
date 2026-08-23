import pytest
import time
from unittest.mock import patch, MagicMock
from datetime import datetime, date
import pandas as pd

import common_lib.config.main_config
import common_lib.connectors.oracle

from app.tools.registry import registry
from app.tools.flow_tool import (
    get_unusual_flow,
    _format_dollar_amount,
    _format_single_flow_summary,
    _FLOW_MEMORY_CACHE,
    CACHE_TTL_SECONDS
)


@pytest.fixture(autouse=True)
def clear_flow_cache():
    _FLOW_MEMORY_CACHE.clear()
    yield
    _FLOW_MEMORY_CACHE.clear()


def test_tool_registry_includes_flow_tool():
    declarations = registry.get_all_declarations()
    tool_names = [d["name"] for d in declarations]
    assert "get_unusual_flow" in tool_names

    decl = next(d for d in declarations if d["name"] == "get_unusual_flow")
    assert "ticker" in decl["parameters"]["properties"]
    assert "lookback_days" in decl["parameters"]["properties"]
    assert "min_premium" in decl["parameters"]["properties"]


def test_format_dollar_amount():
    assert _format_dollar_amount(14_200_000) == "$14.20M"
    assert _format_dollar_amount(780_000) == "$780.00K"
    assert _format_dollar_amount(1_850_000_000) == "$1.85B"
    assert _format_dollar_amount(500) == "$500.00"
    assert _format_dollar_amount(0) == "$0.00"
    assert _format_dollar_amount(None) == "$0.00"
    assert _format_dollar_amount("$10.5M") == "$10.5M"


def test_format_single_flow_summary_with_data():
    sample_df = pd.DataFrame([
        {
            "FLOW_ID": "f1",
            "TRADE_DATE": "2026-08-17",
            "SYMBOL": "PLTR",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 185.0,
            "STRIKE_OTM_PCT": 7.0,
            "EXPIRATION_DATE": "2027-12-17",
            "OPEN_INTEREST": 4114,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 14_200_000.0,
            "NET_SCORE": 1.0,
            "CREATED_AT": datetime.now()
        },
        {
            "FLOW_ID": "f2",
            "TRADE_DATE": "2026-08-13",
            "SYMBOL": "PLTR",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 180.0,
            "STRIKE_OTM_PCT": 1.0,
            "EXPIRATION_DATE": "2027-12-17",
            "OPEN_INTEREST": 1957,
            "IS_UNUSUAL_OI": 1,
            "PREMIUM": 21_700_000.0,
            "NET_SCORE": 1.0,
            "CREATED_AT": datetime.now()
        },
        {
            "FLOW_ID": "f3",
            "TRADE_DATE": "2026-08-11",
            "SYMBOL": "PLTR",
            "ORDER_TYPE": "BUY_PUT",
            "STRIKE_PRICE": 140.0,
            "STRIKE_OTM_PCT": -20.0,
            "EXPIRATION_DATE": "2026-12-18",
            "OPEN_INTEREST": 32893,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 18_300_000.0,
            "NET_SCORE": 1.0,
            "CREATED_AT": datetime.now()
        }
    ])

    summary = _format_single_flow_summary("PLTR", sample_df, lookback_days=30)
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: PLTR (Last 30 Days)]" in summary
    assert "• Total Net Flow Volume: $54.20M" in summary
    assert "Call Flow: $35.90M [66.2%]" in summary
    assert "Put Flow: $18.30M [33.8%]" in summary
    assert "• Flow Sentiment Score: +1.0 | Sentiment: Bullish" in summary
    assert "• High-Conviction Prints:" in summary
    assert "2026-08-13: $21.70M BUY CALL | Strike: $180.00 (+1.0%) | Exp: 2027-12-17 | OI: 1,957 ⚠️" in summary
    assert "2026-08-11: $18.30M BUY PUT | Strike: $140.00 (-20.0%) | Exp: 2026-12-18 | OI: 32,893" in summary


def test_zero_data_fallback():
    # Empty DataFrame
    summary_empty = _format_single_flow_summary("NVDA", pd.DataFrame(), lookback_days=30)
    assert summary_empty == "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: NVDA] No unusual institutional options flow recorded in the past 30 days."

    # None DataFrame
    summary_none = _format_single_flow_summary("AAPL", None, lookback_days=14)
    assert summary_none == "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: AAPL] No unusual institutional options flow recorded in the past 14 days."


@patch("common_lib.connectors.oracle.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_tool_execution(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_load_config.return_value = mock_config

    mock_df = pd.DataFrame([
        {
            "FLOW_ID": "flow1",
            "TRADE_DATE": "2026-08-20",
            "SYMBOL": "TSLA",
            "ORDER_TYPE": "SWEEP_CALL",
            "STRIKE_PRICE": 250.0,
            "STRIKE_OTM_PCT": 5.0,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 5000,
            "IS_UNUSUAL_OI": 1,
            "PREMIUM": 5_000_000.0,
            "NET_SCORE": 2.0,
            "CREATED_AT": datetime.now()
        }
    ])
    mock_get_flow.return_value = mock_df

    res = get_unusual_flow(ticker="TSLA", lookback_days=15, min_premium=100000.0)
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: TSLA (Last 15 Days)]" in res
    assert "• Total Net Flow Volume: $5.00M" in res
    assert "SWEEP CALL" in res
    assert "⚠️" in res

    # Verify mock call parameters
    mock_get_flow.assert_called_once_with(
        config=mock_config,
        symbol="TSLA",
        lookback_days=15,
        min_premium=100000.0
    )


@patch("common_lib.connectors.oracle.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_caching(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_load_config.return_value = mock_config

    mock_df = pd.DataFrame([
        {
            "FLOW_ID": "flow1",
            "TRADE_DATE": "2026-08-20",
            "SYMBOL": "AMD",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 170.0,
            "STRIKE_OTM_PCT": 3.0,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 1200,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 2_500_000.0,
            "NET_SCORE": 1.0,
            "CREATED_AT": datetime.now()
        }
    ])
    mock_get_flow.return_value = mock_df

    # First call: cache miss, triggers DB query
    res1 = get_unusual_flow(ticker="AMD", lookback_days=30)
    assert mock_get_flow.call_count == 1
    assert "AMD" in res1

    # Second call: cache hit, should NOT call DB again
    res2 = get_unusual_flow(ticker="AMD", lookback_days=30)
    assert mock_get_flow.call_count == 1
    assert res1 == res2

    # Force refresh bypasses cache
    res3 = get_unusual_flow(ticker="AMD", lookback_days=30, force_refresh=True)
    assert mock_get_flow.call_count == 2
    assert res1 == res3


@patch("common_lib.connectors.oracle.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_batch_tickers(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_load_config.return_value = mock_config

    def side_effect(config, symbol, lookback_days, min_premium):
        if symbol == "AAPL":
            return pd.DataFrame([{
                "FLOW_ID": "a1",
                "TRADE_DATE": "2026-08-20",
                "SYMBOL": "AAPL",
                "ORDER_TYPE": "BUY_CALL",
                "STRIKE_PRICE": 230.0,
                "STRIKE_OTM_PCT": 2.0,
                "EXPIRATION_DATE": "2026-09-18",
                "OPEN_INTEREST": 8000,
                "IS_UNUSUAL_OI": 0,
                "PREMIUM": 8_000_000.0,
                "NET_SCORE": 1.0,
                "CREATED_AT": datetime.now()
            }])
        return pd.DataFrame()

    mock_get_flow.side_effect = side_effect

    res = get_unusual_flow(ticker="AAPL, MSFT", lookback_days=30)
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: AAPL (Last 30 Days)]" in res
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: MSFT] No unusual institutional options flow recorded in the past 30 days." in res


def test_get_unusual_flow_fault_isolation():
    # Calling with empty or invalid ticker does not throw
    res = get_unusual_flow(ticker="")
    assert "No valid ticker provided" in res

    # Even if DB connection fails, returns graceful response
    with patch("common_lib.connectors.oracle.get_unusual_flow", side_effect=Exception("Database connection timeout")):
        res_fail = get_unusual_flow(ticker="AMZN", lookback_days=7)
        assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: AMZN] No unusual institutional options flow recorded in the past 7 days." in res_fail
