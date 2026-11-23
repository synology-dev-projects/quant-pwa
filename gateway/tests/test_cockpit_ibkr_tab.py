import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token
from app.engine.service import get_ibkr_strike_distribution, StrikeDistributionResponse

client = TestClient(app)


@pytest.fixture
def auth_header():
    token, _ = create_session_token(expires_in_hours=6)
    return {"Authorization": f"Bearer {token}"}


def _mock_cboe_chain():
    return {
        ("2026-12-18", 580.0, "C"): {"open_interest": 12000, "iv": 0.22, "und_price": 580.0},
        ("2026-12-18", 580.0, "P"): {"open_interest": 10000, "iv": 0.24, "und_price": 580.0},
        ("2026-12-18", 590.0, "C"): {"open_interest": 18000, "iv": 0.21, "und_price": 580.0},
        ("2026-12-18", 570.0, "P"): {"open_interest": 15000, "iv": 0.25, "und_price": 580.0},
    }


def _mock_te_raw(ticker="NVDA", spot=217.5):
    return {
        "ticker": ticker,
        "spot_price": spot,
        "call_wall": spot + 10.0,
        "put_wall": spot - 10.0,
        "zero_gex_level": spot - 2.0,
        "call_put_ratio": 1.3,
        "strikes": [
            {
                "strike": spot,
                "expirations": {
                    "2026-12-18": {"call_gex": 500000.0, "put_gex": 300000.0, "call_dex": 250000.0, "put_dex": 150000.0}
                },
            }
        ],
    }


def test_get_ibkr_strike_distribution_schema():
    """Verify get_ibkr_strike_distribution produces valid StrikeDistributionResponse with all required keys."""
    with patch("app.engine.service._IBKR_STRIKE_CACHE", {}), \
         patch("common_lib.connectors.cboe_oi.fetch_cboe_delayed_data", return_value=_mock_cboe_chain()):
        res = get_ibkr_strike_distribution("SPY", max_dte=30, strike_range=25, spot_hint=580.0)
    assert isinstance(res, StrikeDistributionResponse)
    assert res.ticker == "SPY"
    assert res.is_fallback is False
    assert res.spot_price > 0.0
    assert res.call_wall > 0.0
    assert res.put_wall > 0.0
    assert res.zero_gex_level > 0.0
    assert len(res.strikes) > 0

    first_strike = res.strikes[0]
    assert hasattr(first_strike, "strike")
    assert hasattr(first_strike, "call_gex")
    assert hasattr(first_strike, "put_gex")
    assert hasattr(first_strike, "net_gex")
    assert hasattr(first_strike, "call_dex")
    assert hasattr(first_strike, "put_dex")
    assert hasattr(first_strike, "net_dex")


def test_cockpit_data_contains_both_tradingedge_and_ibkr_gex(auth_header):
    """Verify /api/cockpit/data returns both gex (TradingEdge) and ibkr_gex (IBKR) with matching schemas."""
    with patch("app.engine.service.fetch_raw_data_for_ticker", return_value=_mock_te_raw("NVDA", 217.5)), \
         patch("app.engine.service._IBKR_STRIKE_CACHE", {}), \
         patch("common_lib.connectors.cboe_oi.fetch_cboe_delayed_data", return_value=_mock_cboe_chain()):
        response = client.get("/api/cockpit/data?ticker=NVDA", headers=auth_header)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["ticker"] == "NVDA"

    # Both GEX distributions must be present
    assert "gex" in data
    assert "ibkr_gex" in data
    assert data["ibkr_gex"].get("is_fallback") is False

    te_gex = data["gex"]
    ib_gex = data["ibkr_gex"]

    # Invariant: Both sources must relay the exact same core structural keys
    for key in ["spot_price", "call_wall", "put_wall", "zero_gex_level", "net_gex", "net_dex", "strikes"]:
        assert key in te_gex, f"Missing {key} in TradingEdge GEX"
        assert key in ib_gex, f"Missing {key} in IBKR GEX"

    assert len(te_gex["strikes"]) > 0
    assert len(ib_gex["strikes"]) > 0

    # Verify strike detail layout matches
    te_first = te_gex["strikes"][0]
    ib_first = ib_gex["strikes"][0]
    for field in ["strike", "call_gex", "put_gex", "net_gex", "call_dex", "put_dex", "net_dex"]:
        assert field in te_first
        assert field in ib_first


def test_cockpit_data_post_contains_both_sources(auth_header):
    """Verify POST /api/cockpit/data also returns both gex and ibkr_gex."""
    response = client.post("/api/cockpit/data", json={"ticker": "QQQ"}, headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert "gex" in data
    assert "ibkr_gex" in data
    assert data["ibkr_gex"]["ticker"] == "QQQ"
