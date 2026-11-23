from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token
from app.engine.service import get_strike_distribution, get_ibkr_strike_distribution

client = TestClient(app)


def test_tradingedge_failure_returns_error_not_synthetic_fallback():
    """When TradingEdge returns None, get_strike_distribution must NOT synthesize fake strikes."""
    with patch("app.engine.service.fetch_raw_data_for_ticker", return_value=None):
        res = get_strike_distribution("SPY", force_refresh=True)

    assert res.strikes == [], "Synthetic fallback strikes must not be returned when TradingEdge fails"
    assert res.expirations == []
    assert res.is_fallback is False
    assert res.error_code is not None and len(res.error_code) > 0
    assert res.error_message is not None and len(res.error_message) > 0
    assert res.error_traceback is not None and len(res.error_traceback) > 0


def test_ibkr_failure_returns_error_not_synthetic_fallback():
    """When IBKR/CBOE raises an exception, get_ibkr_strike_distribution must return error_code & traceback."""
    with patch("app.engine.service._IBKR_STRIKE_CACHE", {}), \
         patch("common_lib.connectors.cboe_oi.fetch_cboe_delayed_data", side_effect=RuntimeError("CBOE 503 outage")):
        res = get_ibkr_strike_distribution("NVDA", force_refresh=True)

    assert res.strikes == [], "Synthetic fallback strikes must not be returned when IBKR/CBOE fails"
    assert res.error_code is not None
    assert "CBOE 503 outage" in (res.error_message or "")
    assert "RuntimeError" in (res.error_traceback or "")


def test_cockpit_endpoint_exposes_errors_without_resilient_fallback():
    """GET /api/cockpit/data must surface real error_code and error_traceback instead of synthetic Front Expiry strikes."""
    token, _ = create_session_token(expires_in_hours=1)
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.routers.cockpit.get_strike_distribution", side_effect=RuntimeError("TE auth rejected")), \
         patch("app.routers.cockpit.get_ibkr_strike_distribution", side_effect=RuntimeError("IBKR offline")), \
         patch("app.routers.cockpit._fetch_postgres_flow_sync", return_value=None):
        resp = client.get("/api/cockpit/data?ticker=SPY", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["gex"]["strikes"] == []
    assert body["gex"].get("error_code") is not None
    assert "TE auth rejected" in (body["gex"].get("error_message") or "")
    assert "RuntimeError" in (body["gex"].get("error_traceback") or "")
    assert body["ibkr_gex"]["strikes"] == []
    assert body["ibkr_gex"].get("error_code") is not None
    assert "IBKR offline" in (body["ibkr_gex"].get("error_message") or "")
    assert "RuntimeError" in (body["ibkr_gex"].get("error_traceback") or "")
