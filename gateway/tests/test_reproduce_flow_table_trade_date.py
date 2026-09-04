import pytest
import pandas as pd
from app.tools.flow_tool import format_pure_flow_table


def test_format_pure_flow_table_includes_trade_date():
    """
    In-Situ Reproduction Test: BUG - Options flow tables must show the Trade Date.
    """
    df = pd.DataFrame([
        {
            "FLOW_ID": "abc123456789",
            "TRADE_DATE": "2026-08-26",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 255.0,
            "STRIKE_OTM_PCT": 22.0,
            "EXPIRATION_DATE": "2026-10-16",
            "OPEN_INTEREST": 12900,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 1500000.0,
            "NET_SCORE": 0.0,
        },
        {
            "FLOW_ID": "def987654321",
            "TRADE_DATE": "2026-08-27",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "SELL_PUT",
            "STRIKE_PRICE": 170.0,
            "STRIKE_OTM_PCT": -5.0,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 8500,
            "IS_UNUSUAL_OI": 1,
            "PREMIUM": 2300000.0,
            "NET_SCORE": 0.5,
        }
    ])

    table_md = format_pure_flow_table(df, date_label="NVDA Flow")

    # The table header must contain Trade Date (or Date)
    header_line = table_md.splitlines()[0]
    assert "Trade Date" in header_line or "Date" in header_line, (
        f"Header line does not contain 'Trade Date': {header_line}"
    )

    # The table rows must render the corresponding trade dates
    assert "2026-08-26" in table_md, "Trade date '2026-08-26' missing from flow table rows"
    assert "2026-08-27" in table_md, "Trade date '2026-08-27' missing from flow table rows"
