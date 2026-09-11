import pytest
from datetime import date
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token

client = TestClient(app)


def test_radar_auth_rejection_missing_header():
    res = client.get("/api/radar/unified-table")
    assert res.status_code == 401
    assert "Authorization" in res.json().get("detail", "")


def test_radar_auth_rejection_invalid_token():
    res = client.get("/api/radar/unified-table", headers={"Authorization": "Bearer bad-token"})
    assert res.status_code == 401


def test_get_radar_dates():
    token, _ = create_session_token()
    res = client.get("/api/radar/dates", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    dates = res.json()
    assert isinstance(dates, list)
    if dates:
        assert "2026-09-09" in dates


def test_get_unified_radar_table_structure_and_metrics():
    token, _ = create_session_token()
    res = client.get("/api/radar/unified-table", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()

    assert "session_date" in data
    assert "dates_3d" in data
    assert "dates_7d" in data
    assert "total_tickers" in data
    assert "rows" in data
    assert "available_dates" in data
    assert "generated_at" in data

    assert isinstance(data["rows"], list)
    if data["rows"]:
        row = data["rows"][0]
        # Verify required unified grain and columns
        assert "ticker" in row
        assert "snapshot_date" in row
        assert "spot_price" in row
        assert "formatted_spot_price" in row
        assert "call_put_ratio" in row
        assert "prints_3d" in row
        assert "prints_7d" in row
        assert "premium_3d" in row
        assert "formatted_premium_3d" in row
        assert "premium_7d" in row
        assert "formatted_premium_7d" in row
        assert "call_wall" in row
        assert "formatted_call_wall" in row
        assert "put_wall" in row
        assert "formatted_put_wall" in row
        assert "zero_flip" in row
        assert "formatted_zero_flip" in row
        assert "net_gex" in row
        assert "formatted_net_gex" in row
        assert "gamma_regime" in row

        # Verify types
        assert isinstance(row["ticker"], str)
        assert isinstance(row["prints_3d"], int)
        assert isinstance(row["prints_7d"], int)
        assert isinstance(row["premium_3d"], float)
        assert isinstance(row["premium_7d"], float)
        assert row["formatted_premium_3d"].startswith("$")
        assert row["formatted_premium_7d"].startswith("$")


def test_get_unified_radar_table_specific_date():
    token, _ = create_session_token()
    res = client.get("/api/radar/unified-table?date=2026-09-09", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["session_date"] == "2026-09-09"
    assert len(data["rows"]) > 0

    # Confirm key known tickers are present (e.g. AAPL, NVDA, AMD)
    tickers = {r["ticker"] for r in data["rows"]}
    assert "AAPL" in tickers
    assert "NVDA" in tickers
