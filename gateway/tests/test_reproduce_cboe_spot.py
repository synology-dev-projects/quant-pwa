import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Ensure common-lib is importable
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
COMMON_LIB_PATH = WORKSPACE_ROOT / "common-lib"
if str(COMMON_LIB_PATH) not in sys.path:
    sys.path.insert(0, str(COMMON_LIB_PATH))


def test_reproduce_cboe_spot_price_extraction():
    """
    REPRODUCTION TEST: CBOE Delayed Market Data Underlying Spot Price Extraction
    
    Bug Description:
    When querying GLXY options from CBOE, CBOE returns the underlying stock price
    (`close: 19.09`, `current_price: 18.50`) in payload['data'].
    However, fetch_cboe_delayed_data() fails to attach `und_price` to the returned contract dicts.
    As a consequence, get_ibkr_strike_distribution() finds cboe_spot == 0.0 and falls back
    to the median strike index `all_stks[len(all_stks) // 2]`. For GLXY (71 strikes from 1 to 65),
    this yields 22.0 instead of the real spot price of 19.09!
    
    Expected:
      - fetch_cboe_delayed_data extracts und_price (19.09) from CBOE JSON and attaches it to records.
      - get_ibkr_strike_distribution calculates Greeks with spot_price == 19.09 (NOT median strike 22.0).
    Actual (Prior to Fix):
      - fetch_cboe_delayed_data leaves und_price as None.
      - get_ibkr_strike_distribution returns spot_price == 22.0.
    """
    from common_lib.connectors.cboe_oi import fetch_cboe_delayed_data
    from app.engine.service import get_ibkr_strike_distribution, _IBKR_STRIKE_CACHE

    _IBKR_STRIKE_CACHE.clear()

    # Real CBOE GLXY 71 strike list where index 35 (median) is 22.0
    strikes = [
        1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 7.5, 8.0, 9.0, 10.0, 10.5, 11.0, 11.5,
        12.0, 12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0, 16.5, 17.0, 17.5, 18.0,
        18.5, 19.0, 19.5, 20.0, 20.5, 21.0, 21.5, 22.0, 22.5, 23.0, 23.5, 24.0, 24.5,
        25.0, 25.5, 26.0, 26.5, 27.0, 27.5, 28.0, 28.5, 29.0, 29.5, 30.0, 30.5, 31.0,
        31.5, 32.0, 32.5, 33.0, 33.5, 34.0, 35.0, 36.0, 37.5, 40.0, 42.5, 45.0, 47.5,
        50.0, 55.0, 60.0, 65.0
    ]
    assert len(strikes) == 71
    assert strikes[len(strikes) // 2] == 22.0

    mock_cboe_json = {
        "timestamp": "2026-10-28T16:00:00",
        "data": {
            "symbol": "GLXY",
            "current_price": 18.50,
            "close": 19.09,
            "prev_day_close": 17.18,
            "options": []
        }
    }

    for stk in strikes:
        stk_str = f"{int(stk * 1000):08d}"
        for right in ("C", "P"):
            mock_cboe_json["data"]["options"].append({
                "option": f"GLXY261120{right}{stk_str}",
                "open_interest": 100.0,
                "iv": 0.45,
                "delta": 0.50 if right == "C" else -0.50,
                "gamma": 0.05,
                "bid": 1.0,
                "ask": 1.2,
                "volume": 50.0
            })

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_cboe_json

    with patch("requests.get", return_value=mock_resp):
        # 1. Verify connector attaches und_price
        cboe_data = fetch_cboe_delayed_data("GLXY")
        assert cboe_data, "cboe_data should not be empty"
        first_record = next(iter(cboe_data.values()))
        
        # ASSERTION 1: und_price must be present and match close (19.09) or current_price (18.50)
        assert "und_price" in first_record, "CBOE connector must attach 'und_price' to contract dictionaries"
        assert first_record["und_price"] is not None
        assert abs(first_record["und_price"] - 19.09) < 0.6, f"Expected ~19.09, got {first_record['und_price']}"

        # 2. Verify get_ibkr_strike_distribution uses authentic spot price instead of median strike 22.0
        dist = get_ibkr_strike_distribution("GLXY", max_dte=50, strike_range=25, force_refresh=True, spot_hint=None)
        
        # ASSERTION 2: dist.spot_price must be authentic spot (19.09), NOT median strike 22.0
        assert dist.spot_price != 22.0, "Spot price should NOT be the distorted median strike (22.0)"
        assert abs(dist.spot_price - 19.09) < 0.6, f"Expected spot_price close to 19.09, got {dist.spot_price}"
