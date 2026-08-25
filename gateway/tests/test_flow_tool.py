import pytest
import time
from unittest.mock import patch, MagicMock
from datetime import datetime, date
import pandas as pd

from app.tools.registry import registry
from app.tools.flow_tool import (
    get_unusual_flow,
    _format_dollar_amount,
    format_pure_flow_table,
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
    assert "date" in decl["parameters"]["properties"]
    assert "ticker" in decl["parameters"]["properties"]
    assert "min_premium" in decl["parameters"]["properties"]


def test_format_dollar_amount():
    assert _format_dollar_amount(14_200_000) == "$14.20M"
    assert _format_dollar_amount(780_000) == "$780.00K"
    assert _format_dollar_amount(1_850_000_000) == "$1.85B"
    assert _format_dollar_amount(500) == "$500.00"
    assert _format_dollar_amount(0) == "$0.00"
    assert _format_dollar_amount(None) == "$0.00"
    assert _format_dollar_amount("$10.5M") == "$10.5M"


def test_format_pure_flow_table_with_data():
    sample_df = pd.DataFrame([
        {
            "FLOW_ID": "f1",
            "TRADE_DATE": "2026-08-21",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 130.0,
            "STRIKE_OTM_PCT": 2.0,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 15000,
            "IS_UNUSUAL_OI": 1,
            "PREMIUM": 25_000_000.0,
            "NET_SCORE": 2.0,
            "CREATED_AT": datetime.now()
        },
        {
            "FLOW_ID": "f2",
            "TRADE_DATE": "2026-08-21",
            "SYMBOL": "TSLA",
            "ORDER_TYPE": "BUY_PUT",
            "STRIKE_PRICE": 200.0,
            "STRIKE_OTM_PCT": -5.0,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 8000,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 10_000_000.0,
            "NET_SCORE": -1.5,
            "CREATED_AT": datetime.now()
        }
    ])

    table = format_pure_flow_table(sample_df, "2026-08-21")
    assert "| Symbol | Order Action | Strike | OTM % | Expiration | Open Interest | Premium | Trade Date |" in table
    assert "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |" in table
    assert "| **NVDA** | BUY CALL | $130.00 | +2.0% | 2026-09-18 | 15,000 ⚠️ | $25.00M | 2026-08-21 |" in table
    assert "| **TSLA** | BUY PUT | $200.00 | -5.0% | 2026-09-18 | 8,000 | $10.00M | 2026-08-21 |" in table


def test_format_pure_flow_table_empty():
    table_empty = format_pure_flow_table(pd.DataFrame(), "2026-08-21")
    assert table_empty == "No unusual institutional options flow recorded for '2026-08-21'."

    table_none = format_pure_flow_table(None)
    assert table_none == "No unusual institutional options flow recorded."


@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_default_latest_session(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
    mock_load_config.return_value = mock_config

    mock_df = pd.DataFrame([
        {
            "FLOW_ID": "flow1",
            "TRADE_DATE": "2026-08-21",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 135.0,
            "STRIKE_OTM_PCT": 3.0,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 5000,
            "IS_UNUSUAL_OI": 1,
            "PREMIUM": 5_000_000.0,
            "NET_SCORE": 2.0,
            "CREATED_AT": datetime.now()
        }
    ])
    mock_get_flow.return_value = mock_df

    # Call /flow with no args -> defaults to latest session, 100% completeness (limit=None)
    res = get_unusual_flow()
    assert "| **NVDA** | BUY CALL | $135.00 | +3.0% | 2026-09-18 | 5,000 ⚠️ | $5.00M | 2026-08-21 |" in res

    mock_get_flow.assert_called_once_with(
        config=mock_config,
        date="latest",
        min_premium=0.0,
        limit=None
    )


@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_specific_date(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
    mock_load_config.return_value = mock_config
    mock_get_flow.return_value = pd.DataFrame()

    # /flow 2026-08-21
    get_unusual_flow(date="2026-08-21")
    mock_get_flow.assert_called_with(
        config=mock_config,
        date="2026-08-21",
        min_premium=0.0,
        limit=None
    )


@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_date_range(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
    mock_load_config.return_value = mock_config
    mock_get_flow.return_value = pd.DataFrame()

    # /flow 2026-08-17 to 2026-08-21
    get_unusual_flow(date="2026-08-17 to 2026-08-21", min_premium=500000.0)
    mock_get_flow.assert_called_with(
        config=mock_config,
        date="2026-08-17 to 2026-08-21",
        min_premium=500000.0,
        limit=None
    )


@patch("common_lib.connectors.postgres.get_unusual_flow")
@patch("common_lib.config.main_config.load_config")
def test_get_unusual_flow_named_dates(mock_load_config, mock_get_flow):
    mock_config = MagicMock()
    mock_config.db_type = "postgres"
    mock_load_config.return_value = mock_config
    mock_get_flow.return_value = pd.DataFrame()

    # /flow Friday
    get_unusual_flow(ticker="/flow Friday")
    mock_get_flow.assert_called_with(
        config=mock_config,
        date="Friday",
        min_premium=0.0,
        limit=None
    )

    mock_get_flow.reset_mock()

    # /flow yesterday
    get_unusual_flow(ticker="/flow yesterday")
    mock_get_flow.assert_called_with(
        config=mock_config,
        date="yesterday",
        min_premium=0.0,
        limit=None
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
            "TRADE_DATE": "2026-08-21",
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

    # First call: cache miss
    res1 = get_unusual_flow(date="2026-08-21")
    assert mock_get_flow.call_count == 1
    assert "FLOW_DATE_2026-08-21_0.0" in _FLOW_MEMORY_CACHE
    assert "AMD" in res1

    # Second call: cache hit (no DB queries)
    res2 = get_unusual_flow(date="2026-08-21")
    assert mock_get_flow.call_count == 1
    assert res1 == res2

    # Force refresh bypasses cache
    res3 = get_unusual_flow(date="2026-08-21", force_refresh=True)
    assert mock_get_flow.call_count == 2
    assert res1 == res3


@patch("common_lib.connectors.postgres.get_unusual_flow", side_effect=Exception("Database connection timeout"))
def test_get_unusual_flow_fault_isolation(mock_postgres):
    res_fail = get_unusual_flow(date="2026-08-21")
    assert res_fail == "No unusual institutional options flow recorded for '2026-08-21'."


def test_agent_system_instruction_slash_commands():
    from app.core.agent import SYSTEM_INSTRUCTION_BASE
    assert "/flow" in SYSTEM_INSTRUCTION_BASE
    assert "get_unusual_flow(date=" in SYSTEM_INSTRUCTION_BASE
    assert "PURE DATA INVARIANT" in SYSTEM_INSTRUCTION_BASE
