import pytest
from unittest.mock import MagicMock
from common_lib.connectors.tradingedge.dexgex import extract_raw_data
from app.engine.service import fetch_raw_data_for_ticker, get_strike_distribution


def test_reproduce_delta_chart_raw_extractor_kill_switch():
    """
    Bug reproduction: Cockpit Delta Exposure (DEX) and GEX charts are displaying synthetic/fallback
    data because extract_raw_data in common_lib was hardcoded to return None via a kill switch.
    
    Expected: extract_raw_data must execute requests against config.te_dex_gex_url when session is provided,
    returning the live options chain dictionary instead of None.
    """
    mock_config = MagicMock()
    mock_config.te_dex_gex_url = "https://tools.tradingedge.club/api/dex-gex"

    sample_raw_data = {
        "ticker": "NVDA",
        "spot_price": 225.50,
        "call_wall": 235.00,
        "put_wall": 215.00,
        "call_put_ratio": 1.25,
        "strikes": [
            {
                "strike": 225.0,
                "expirations": {
                    "2026-10-16": {"call_dex": 450000.0, "put_dex": 320000.0, "call_gex": 12000.0, "put_gex": 9000.0}
                }
            }
        ]
    }

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_raw_data
    mock_session.get.return_value = mock_resp

    # Exercise extract_raw_data directly
    result = extract_raw_data(
        config=mock_config,
        session_or_cookie=mock_session,
        ticker="NVDA",
        max_dte=50,
        strike_range=25
    )

    # In RED state: result is None due to kill-switch
    assert result is not None, "extract_raw_data must not return None when valid session and response are available"
    assert result.get("ticker") == "NVDA"
    assert len(result.get("strikes", [])) > 0
    assert result["strikes"][0]["expirations"]["2026-10-16"]["call_dex"] == 450000.0


def test_reproduce_delta_chart_distribution_has_live_dex():
    """
    Bug reproduction: get_strike_distribution must return non-synthetic DEX values
    when raw data is retrieved.
    """
    sample_raw_data = {
        "ticker": "NVDA",
        "spot_price": 225.50,
        "call_wall": 235.00,
        "put_wall": 215.00,
        "call_put_ratio": 1.25,
        "strikes": [
            {
                "strike": 225.0,
                "expirations": {
                    "2026-10-16": {"call_dex": 450000.0, "put_dex": 320000.0, "call_gex": 12000.0, "put_gex": 9000.0}
                }
            }
        ]
    }

    from unittest.mock import patch
    with patch("app.engine.service.fetch_raw_data_for_ticker", return_value=sample_raw_data):
        dist = get_strike_distribution("NVDA", force_refresh=True)
        assert dist.ticker == "NVDA"
        assert len(dist.strikes) == 1
        stk = dist.strikes[0]
        assert stk.strike == 225.0
        assert stk.call_dex == 450000.0
        assert stk.put_dex == 320000.0
        assert stk.net_dex == 130000.0
