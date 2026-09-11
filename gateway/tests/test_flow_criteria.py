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


def test_extract_session_notable_flow_db_sqlite():
    import sqlalchemy as sa
    from app.core.flow_criteria import extract_session_notable_flow_db

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE unusual_option_flow_te (
                flow_id TEXT PRIMARY KEY,
                trade_date TEXT,
                symbol TEXT,
                order_type TEXT,
                strike_price REAL,
                strike_otm_pct REAL,
                expiration_date TEXT,
                premium REAL
            );
        """))
        conn.execute(sa.text("""
            INSERT INTO unusual_option_flow_te VALUES
            ('1', '2026-09-04', 'ORCL', 'BUY_CALL', 177.5, 12.0, '2026-09-11', 1900000.0),
            ('2', '2026-09-04', 'SMH', 'SELL_PUT', 580.0, 2.0, '2027-01-15', 24300000.0),
            ('3', '2026-08-20', 'SMH', 'SELL_PUT', 570.0, 1.0, '2027-01-15', 30000000.0);
        """))

    with engine.connect() as conn:
        tp, otm = extract_session_notable_flow_db(conn, "2026-09-04")
        assert len(tp) >= 1
        assert tp[0]["symbol"] == "SMH"
        assert len(otm) >= 1
        assert otm[0]["symbol"] == "ORCL"
        assert otm[0]["otm_pct"] == 12.0
        assert otm[0]["dte"] == 7


def test_notable_flow_unlimited_prints():
    # Verify that format_notable_flow_markdown does not truncate to 3
    tp_prints = [
        {"symbol": f"SYM{i}", "formatted_premium": f"${10-i}.0M", "rank": i + 1}
        for i in range(6)
    ]
    otm_prints = [
        {"symbol": f"OTM{i}", "otm_pct": 10.0 + i, "dte": 7 + i}
        for i in range(6)
    ]

    md = format_notable_flow_markdown(tp_prints, otm_prints)
    for i in range(6):
        assert f"SYM{i}" in md
        assert f"OTM{i}" in md

    # Verify extract_session_notable_flow_db returns all qualifying rows (>3)
    import sqlalchemy as sa
    from app.core.flow_criteria import extract_session_notable_flow_db

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE unusual_option_flow_te (
                flow_id TEXT PRIMARY KEY,
                trade_date TEXT,
                symbol TEXT,
                order_type TEXT,
                strike_price REAL,
                strike_otm_pct REAL,
                expiration_date TEXT,
                premium REAL
            );
        """))
        for i in range(5):
            conn.execute(sa.text(f"""
                INSERT INTO unusual_option_flow_te VALUES
                ('tp_{i}', '2026-09-04', 'SYM{i}', 'BUY_CALL', 100.0, 2.0, '2026-09-18', {2000000.0 - i * 100000});
            """))
            conn.execute(sa.text(f"""
                INSERT INTO unusual_option_flow_te VALUES
                ('otm_{i}', '2026-09-04', 'OTM{i}', 'BUY_CALL', 120.0, {15.0 + i}, '2026-09-18', 500000.0);
            """))

    with engine.connect() as conn:
        tp, otm = extract_session_notable_flow_db(conn, "2026-09-04")
        # All 10 symbols qualify for all_time_rank <= 3, and all 5 OTM prints qualify.
        # Previously both were capped at 3 with [:3]. Now unlimited prints are preserved.
        assert len(tp) == 10
        assert len(otm) == 5



