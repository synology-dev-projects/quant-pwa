import pytest
from unittest.mock import patch, AsyncMock
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

@patch("app.routers.quant_levels_status.postgres.get_quant_levels")
@patch("app.routers.quant_levels_status.postgres.sql")
@patch("app.routers.quant_levels_status.load_config")
@patch("app.routers.quant_levels_status.get_batch_quotes")
def test_reproduce_spx_spot_parity_prioritizes_gspc(mock_quotes, mock_config, mock_sql, mock_get_levels):
    """
    RED GATE TEST:
    Reproduces spot price desynchronization between candlestick chart and ladder.
    The quant levels status router must request and prioritize '^GSPC' (real-time S&P 500)
    over delayed '^SPX' (15m delayed CBOE index).
    If quotes contains both '^GSPC' (7735.98) and '^SPX' (7728.76),
    spot_price must be 7735.98, NOT 7728.76.
    """
    mock_sql.return_value = pd.DataFrame([{"d": "2026-09-21"}])
    mock_get_levels.return_value = pd.DataFrame([
        {
            "START_LVL_PRICE": 7748.0,
            "END_LVL_PRICE": 7756.0,
            "BUY_SELL_IND": "SELL",
            "COMMENTS": "Major resistance"
        },
        {
            "START_LVL_PRICE": 7728.0,
            "END_LVL_PRICE": 7737.0,
            "BUY_SELL_IND": "SELL",
            "COMMENTS": "Intraday sell corridor"
        },
        {
            "START_LVL_PRICE": 7718.0,
            "END_LVL_PRICE": 7722.0,
            "BUY_SELL_IND": "BUY",
            "COMMENTS": "Key support"
        }
    ])

    mock_quotes.return_value = {
        "^GSPC": {"price": 7735.98, "ticker": "^GSPC"},
        "^SPX": {"price": 7728.76, "ticker": "^SPX"},
        "SPX": {"price": 7728.76, "ticker": "SPX"}
    }

    resp = client.get("/api/quant-levels/data?ticker=SPX")
    assert resp.status_code == 200
    data = resp.json()

    # 1. Assert ^GSPC was queried in quote_syms
    call_tickers = mock_quotes.call_args[0][0]
    assert "^GSPC" in call_tickers, f"Expected '^GSPC' in quote_syms, got {call_tickers}"
    # Assert ^GSPC is positioned before ^SPX
    assert call_tickers.index("^GSPC") < call_tickers.index("^SPX"), f"'^GSPC' should precede '^SPX' in {call_tickers}"

    # 2. Assert spot_price is the real-time ^GSPC price (7735.98), NOT delayed ^SPX (7728.76)
    assert data["spot_price"] == 7735.98, f"Expected spot_price 7735.98, got {data['spot_price']}"
