import pytest
from datetime import date
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token

client = TestClient(app)


def test_scanner_auth_rejection_missing_header():
    res = client.get("/api/scanner/latest")
    assert res.status_code == 401
    assert "Authorization" in res.json().get("detail", "")


def test_scanner_auth_rejection_invalid_passcode():
    res = client.get("/api/scanner/latest", headers={"Authorization": "Bearer bad-token"})
    assert res.status_code == 401


def test_get_available_scan_dates():
    token, _ = create_session_token()
    res = client.get("/api/scanner/dates", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    dates = res.json()
    assert isinstance(dates, list)
    # 2026-09-04 was populated by the pipeline run
    if dates:
        assert "2026-09-04" in dates


def test_get_latest_confluence_scan_returns_precomputed_data():
    token, _ = create_session_token()
    res = client.get("/api/scanner/latest", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()

    assert "scan_date" in data
    assert "summary" in data
    assert "rows" in data
    assert "count" in data

    if data["rows"]:
        first_row = data["rows"][0]
        # Verify 100% pre-computed fields are present
        assert "ticker" in first_row
        assert "formatted_spot_price" in first_row
        assert "formatted_flow_premium" in first_row
        assert "call_premium_pct" in first_row
        assert "flow_bias" in first_row
        assert "gamma_regime" in first_row
        assert "formatted_net_gex" in first_row
        assert "wall_spread_range" in first_row
        assert "confluence_status" in first_row
        assert "confluence_score" in first_row
        assert "confluence_rationale" in first_row

        # Verify summary
        summary = data["summary"]
        assert summary is not None
        assert "session_label" in summary
        assert "total_scanned_count" in summary
        assert "market_regime_summary" in summary
        assert "top_whale_ticker" in summary


def test_get_confluence_scan_by_date():
    token, _ = create_session_token()
    res = client.get("/api/scanner/by-date?date=2026-09-04", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["scan_date"] == "2026-09-04"


def test_get_confluence_scan_by_date_empty():
    token, _ = create_session_token()
    res = client.get("/api/scanner/by-date?date=1990-01-01", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["summary"] is None
    assert data["rows"] == []
    assert data["count"] == 0
