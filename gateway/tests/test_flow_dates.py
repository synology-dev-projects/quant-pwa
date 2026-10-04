import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token

client = TestClient(app)


def test_flow_dates_requires_auth():
    """Verify that /api/flow/dates rejects unauthenticated requests."""
    res = client.get("/api/flow/dates")
    assert res.status_code == 401


def test_flow_dates_returns_list():
    """Verify that /api/flow/dates returns a list of distinct trade session dates in DESC order."""
    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/flow/dates", headers=headers)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    dates = res.json()
    assert isinstance(dates, list)
    assert len(dates) > 0, "Expected at least one session date in available dates"
    # Ensure all items are strings formatted as YYYY-MM-DD
    for d in dates:
        assert isinstance(d, str)
        assert len(d) == 10
        assert d[4] == "-" and d[7] == "-"
    # Ensure descending sort
    assert dates == sorted(dates, reverse=True), "Available dates must be in descending order"


def test_flow_aggregate_includes_available_dates():
    """Verify that /api/flow/aggregate response includes available_dates list."""
    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/flow/aggregate", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "available_dates" in data
    assert isinstance(data["available_dates"], list)
    assert len(data["available_dates"]) > 0


def test_flow_aggregate_with_historical_as_of_date():
    """Verify querying /api/flow/aggregate with historical date."""
    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    # First fetch available dates
    dates_res = client.get("/api/flow/dates", headers=headers)
    assert dates_res.status_code == 200
    dates = dates_res.json()
    assert len(dates) >= 2, "Expected multiple session dates"
    historical_date = dates[1] # previous day

    res = client.get(f"/api/flow/aggregate?as_of_date={historical_date}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["as_of_date"] == historical_date
    assert "available_dates" in data
    assert isinstance(data["available_dates"], list)
