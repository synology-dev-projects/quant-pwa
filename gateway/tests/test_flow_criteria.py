import pytest
from app.core.flow_criteria import (
    format_currency,
    format_dte_exp,
    format_rank_suffix,
    format_notable_flow_markdown,
    extract_ticker_notable_flow,
    TOP_PREMIUM_RANKS,
    NOTABLE_OTM_MIN_PCT,
    NOTABLE_OTM_MAX_DTE,
)


def test_formatting_helpers():
    assert format_currency(15500000) == "$15.5M"
    assert format_currency(1200000000) == "$1.20B"
    assert format_currency(750000) == "$750K"
    assert format_currency(None) == "$0"

    assert format_dte_exp(0) == "exp 0 days"
    assert format_dte_exp(3) == "exp 3 days"
    assert format_dte_exp(7) == "exp 1 week"
    assert format_dte_exp(14) == "exp 2 weeks"
    assert format_dte_exp(21) == "exp 3 weeks"

    assert format_rank_suffix(1) == "1st"
    assert format_rank_suffix(2) == "2nd"
    assert format_rank_suffix(3) == "3rd"
    assert format_rank_suffix(4) == "4th"


def test_notable_flow_markdown_generation_with_prints():
    top_premium = [
        {"symbol": "NVDA", "formatted_premium": "$23.1M", "rank": 1},
        {"symbol": "AMD", "formatted_premium": "$18.5M", "rank": 2},
    ]
    notable_otm = [
        {"symbol": "TSLA", "otm_pct": 15.0, "dte": 12},
    ]

    md = format_notable_flow_markdown(top_premium, notable_otm)
    assert "• **Notable Flow**:" in md
    assert "• **TOP PREMIUM**:" in md
    assert "- NVDA $23.1M PREMIUM (1st)" in md
    assert "- AMD $18.5M PREMIUM (2nd)" in md
    assert "• **NOTABLE OTM**:" in md
    assert "- TSLA 15% OTM exp 2 weeks" in md


def test_notable_flow_markdown_generation_empty_fallbacks():
    md = format_notable_flow_markdown([], [])
    expected = (
        "• **Notable Flow**:\n"
        "  • **TOP PREMIUM**:\n"
        "    - NONE FOUND\n"
        "  • **NOTABLE OTM**:\n"
        "    - NONE FOUND"
    )
    assert md == expected


def test_extract_ticker_notable_flow_strict_segregation_and_session_date():
    records = [
        # Session date records (2026-09-04)
        {
            "FLOW_ID": 1,
            "TRADE_DATE": "2026-09-04",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 205.0,  # 205 vs spot 200 is 2.5% OTM (not notable OTM)
            "EXPIRATION_DATE": "2026-09-18",
            "PREMIUM": 20000000.0,
        },
        {
            "FLOW_ID": 2,
            "TRADE_DATE": "2026-09-04",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_PUT",
            "STRIKE_PRICE": 180.0,  # 180 vs spot 200 is 10% OTM put
            "EXPIRATION_DATE": "2026-09-18",
            "PREMIUM": 5000000.0,
        },
        # Historical records from prior sessions (ranks #1, #2, #3 all-time)
        {
            "FLOW_ID": 3,
            "TRADE_DATE": "2026-08-20",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 150.0,
            "EXPIRATION_DATE": "2026-09-18",
            "PREMIUM": 50000000.0,  # #1 all-time
        },
        {
            "FLOW_ID": 4,
            "TRADE_DATE": "2026-08-21",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 160.0,
            "EXPIRATION_DATE": "2026-09-18",
            "PREMIUM": 15000000.0,  # #3 all-time (after the $20M print which is #2)
        },
        {
            "FLOW_ID": 5,
            "TRADE_DATE": "2026-08-22",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 170.0,
            "EXPIRATION_DATE": "2026-09-18",
            "PREMIUM": 10000000.0,  # #4 all-time (pushing the $5M print to #5)
        },
    ]

    spot = 200.0
    top_prem, otm = extract_ticker_notable_flow(records, spot, session_date="2026-09-04")

    # The 2026-09-04 BUY_CALL ($20M) is #2 all time behind the $50M print
    assert len(top_prem) == 1
    assert top_prem[0]["symbol"] == "NVDA"
    assert top_prem[0]["rank"] == 2
    assert top_prem[0]["formatted_premium"] == "$20.0M"

    # The 2026-09-04 BUY_PUT ($5M, strike 180 vs spot 200 is 10% OTM, 14 DTE)
    assert len(otm) == 1
    assert otm[0]["symbol"] == "NVDA"
    assert otm[0]["strike"] == 180.0
    assert otm[0]["otm_pct"] == 10.0
    assert otm[0]["dte"] == 14
