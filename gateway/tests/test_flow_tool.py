import pytest
import time
from unittest.mock import patch, MagicMock
from datetime import datetime, date
import pandas as pd

import sys
from pathlib import Path

pipeline_dir = Path(__file__).resolve().parents[3] / "unusual-option-flow-pipeline"
if pipeline_dir.exists() and str(pipeline_dir) not in sys.path:
    sys.path.insert(0, str(pipeline_dir))

import common_lib.config.main_config
import common_lib.connectors.oracle
import common_lib.connectors.postgres

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


@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_tool_execution(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
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

    # Verify mock call parameters uses batch symbols list
    mock_get_flow.assert_called_once_with(
        config=mock_config,
        symbols=["TSLA"],
        lookback_days=15,
        min_premium=100000.0
    )


@patch("common_lib.connectors.oracle.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_oracle_routing(mock_load_config, mock_oracle_flow):
    mock_config = MagicMock()
    mock_config.db_type = "oracle"
    mock_load_config.return_value = mock_config

    mock_df = pd.DataFrame([
        {
            "FLOW_ID": "flow_ora_1",
            "TRADE_DATE": "2026-08-20",
            "SYMBOL": "SPY",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 550.0,
            "STRIKE_OTM_PCT": 1.0,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 10000,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 3_000_000.0,
            "NET_SCORE": 1.5,
            "CREATED_AT": datetime.now()
        }
    ])
    mock_oracle_flow.return_value = mock_df

    res = get_unusual_flow(ticker="SPY", lookback_days=10)
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: SPY (Last 10 Days)]" in res
    assert mock_oracle_flow.call_count == 1
    mock_oracle_flow.assert_called_once_with(
        config=mock_config,
        symbols=["SPY"],
        lookback_days=10,
        min_premium=0.0
    )


@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_caching(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
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

    # Second call: cache hit, should NOT call DB again (0ms latency, zero DB queries)
    res2 = get_unusual_flow(ticker="AMD", lookback_days=30)
    assert mock_get_flow.call_count == 1
    assert res1 == res2

    # Force refresh bypasses cache
    res3 = get_unusual_flow(ticker="AMD", lookback_days=30, force_refresh=True)
    assert mock_get_flow.call_count == 2
    assert res1 == res3


@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_batch_tickers(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
    mock_load_config.return_value = mock_config

    # Return multi-ticker DataFrame in a single flight
    mock_df = pd.DataFrame([
        {
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
        }
    ])
    mock_get_flow.return_value = mock_df

    res = get_unusual_flow(ticker="AAPL, MSFT", lookback_days=30)
    # Verify exact single query with both symbols
    assert mock_get_flow.call_count == 1
    mock_get_flow.assert_called_once_with(
        config=mock_config,
        symbols=["AAPL", "MSFT"],
        lookback_days=30,
        min_premium=0.0
    )
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: AAPL (Last 30 Days)]" in res
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: MSFT] No unusual institutional options flow recorded in the past 30 days." in res


@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_partial_cache_hit(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
    mock_load_config.return_value = mock_config

    # First warm the cache for AAPL
    mock_get_flow.return_value = pd.DataFrame([{
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
    get_unusual_flow(ticker="AAPL", lookback_days=30)
    assert mock_get_flow.call_count == 1

    # Now query AAPL and NVDA: only NVDA should be queried
    mock_get_flow.reset_mock()
    mock_get_flow.return_value = pd.DataFrame([{
        "FLOW_ID": "n1",
        "TRADE_DATE": "2026-08-20",
        "SYMBOL": "NVDA",
        "ORDER_TYPE": "BUY_CALL",
        "STRIKE_PRICE": 130.0,
        "STRIKE_OTM_PCT": 4.0,
        "EXPIRATION_DATE": "2026-09-18",
        "OPEN_INTEREST": 15000,
        "IS_UNUSUAL_OI": 1,
        "PREMIUM": 12_000_000.0,
        "NET_SCORE": 2.0,
        "CREATED_AT": datetime.now()
    }])

    res = get_unusual_flow(ticker="AAPL, NVDA", lookback_days=30)
    assert mock_get_flow.call_count == 1
    mock_get_flow.assert_called_once_with(
        config=mock_config,
        symbols=["NVDA"],
        lookback_days=30,
        min_premium=0.0
    )
    assert "AAPL" in res
    assert "NVDA" in res


@patch("src.extract.extract_flow_for_symbol")
@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_live_fallback(mock_load_config, mock_get_flow, mock_extract):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
    mock_load_config.return_value = mock_config
    mock_get_flow.return_value = pd.DataFrame()  # Empty PostgreSQL DB response

    mock_extract.return_value = [
        {
            "trade_date": "2026-08-22",
            "order_type": "Buy Call",
            "symbol": "META",
            "strike": "600.00 (5 %)",
            "exp": "2026-10-16",
            "oi": "3500 ⚠️",
            "is_unusual_oi": 1,
            "premium": "4.5M",
            "net_score": 1.5
        }
    ]

    res = get_unusual_flow(ticker="META", lookback_days=30)
    assert mock_get_flow.call_count == 1
    assert mock_extract.call_count == 1
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: META (Last 30 Days)]" in res
    assert "$4.50M" in res
    assert "BUY CALL" in res


@patch("src.extract.extract_flow_for_symbol", side_effect=Exception("Network error"))
@patch("common_lib.connectors.postgres.get_unusual_flow", side_effect=Exception("Database connection timeout"))
def test_get_unusual_flow_fault_isolation(mock_postgres, mock_extract):
    # Calling with empty or invalid ticker does not throw
    res = get_unusual_flow(ticker="")
    assert "No valid ticker provided" in res

    # Even if DB connection and live fallback fail, returns graceful fallback response without raising
    res_fail = get_unusual_flow(ticker="AMZN", lookback_days=7)
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: AMZN] No unusual institutional options flow recorded in the past 7 days." in res_fail


def test_agent_system_instruction_slash_commands():
    from app.core.agent import SYSTEM_INSTRUCTION_BASE
    assert "/flow <ticker>" in SYSTEM_INSTRUCTION_BASE
    assert "get_unusual_flow(ticker=" in SYSTEM_INSTRUCTION_BASE
    assert "/gex <ticker>" in SYSTEM_INSTRUCTION_BASE
    assert "/strikes <ticker>" in SYSTEM_INSTRUCTION_BASE


@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_slash_command_prompt_handling(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
    mock_load_config.return_value = mock_config
    mock_get_flow.return_value = pd.DataFrame()

    # Single ticker with /flow slash command
    res1 = get_unusual_flow(ticker="/flow NVDA", lookback_days=30)
    assert mock_get_flow.call_count == 1
    mock_get_flow.assert_called_with(
        config=mock_config,
        symbols=["NVDA"],
        lookback_days=30,
        min_premium=0.0
    )
    assert "NVDA" in res1

    mock_get_flow.reset_mock()

    # Multi-ticker with /flow prefixes and dollar signs
    res2 = get_unusual_flow(ticker="/flow $AAPL, /flow $TSLA", lookback_days=14)
    assert mock_get_flow.call_count == 1
    mock_get_flow.assert_called_with(
        config=mock_config,
        symbols=["AAPL", "TSLA"],
        lookback_days=14,
        min_premium=0.0
    )
    assert "AAPL" in res2
    assert "TSLA" in res2


@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_multi_ticker_resolution_and_deduplication(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
    mock_load_config.return_value = mock_config

    mock_df = pd.DataFrame([
        {
            "FLOW_ID": "flow_aapl",
            "TRADE_DATE": "2026-08-22",
            "SYMBOL": "AAPL",
            "ORDER_TYPE": "SWEEP_CALL",
            "STRIKE_PRICE": 230.0,
            "STRIKE_OTM_PCT": 2.5,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 5000,
            "IS_UNUSUAL_OI": 1,
            "PREMIUM": 6_500_000.0,
            "NET_SCORE": 1.5,
            "CREATED_AT": datetime.now()
        },
        {
            "FLOW_ID": "flow_googl",
            "TRADE_DATE": "2026-08-22",
            "SYMBOL": "GOOGL",
            "ORDER_TYPE": "BUY_PUT",
            "STRIKE_PRICE": 165.0,
            "STRIKE_OTM_PCT": -3.0,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 3200,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 4_200_000.0,
            "NET_SCORE": -1.0,
            "CREATED_AT": datetime.now()
        }
    ])
    mock_get_flow.return_value = mock_df

    # Query with duplicates and mixed formatting
    res = get_unusual_flow(ticker=" AAPL, MSFT, $AAPL , GOOGL, msft ", lookback_days=30)

    # Verify query was called once with deduplicated tickers preserving order
    assert mock_get_flow.call_count == 1
    mock_get_flow.assert_called_once_with(
        config=mock_config,
        symbols=["AAPL", "MSFT", "GOOGL"],
        lookback_days=30,
        min_premium=0.0
    )

    # Check that all 3 tickers have formatted sections
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: AAPL (Last 30 Days)]" in res
    assert "$6.50M" in res
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: MSFT] No unusual institutional options flow recorded in the past 30 days." in res
    assert "[INSTITUTIONAL UNUSUAL OPTIONS FLOW: GOOGL (Last 30 Days)]" in res
    assert "$4.20M" in res
    assert "Bearish" in res

