import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token

client = TestClient(app)


def test_flow_aggregate_requires_auth():
    """Verify that /api/flow/aggregate rejects unauthenticated requests."""
    res = client.get("/api/flow/aggregate")
    assert res.status_code == 401


def test_flow_aggregate_structure():
    """Verify the schema and sorting invariants of /api/flow/aggregate."""
    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/flow/aggregate", headers=headers)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    data = res.json()
    assert "as_of_date" in data
    assert "latest_market_day" in data
    assert "window_3d" in data
    assert "window_1w" in data
    assert "window_7d" in data

    for window_key in ("window_3d", "window_1w", "window_7d"):
        win = data[window_key]
        assert "market_dates" in win
        assert "top_premium_bullish" in win
        assert "top_hits_bullish" in win
        assert "top_premium_bearish" in win
        assert "top_hits_bearish" in win

        if window_key in ("window_1w", "window_7d"):
            assert len(win["market_dates"]) <= 5, f"Expected 1W window to have at most 5 sessions, got {len(win['market_dates'])}"

        # Invariant: At most 5 items per section
        assert len(win["top_premium_bullish"]) <= 5
        assert len(win["top_hits_bullish"]) <= 5
        assert len(win["top_premium_bearish"]) <= 5
        assert len(win["top_hits_bearish"]) <= 5

        # Invariant: Top Bullish Premium must be sorted by total_premium DESC
        prems = [item["total_premium"] for item in win["top_premium_bullish"]]
        assert prems == sorted(prems, reverse=True), f"{window_key} top_premium_bullish not sorted DESC"

        # Invariant: Top Bearish Premium must be sorted by total_premium DESC
        bear_prems = [item["total_premium"] for item in win["top_premium_bearish"]]
        assert bear_prems == sorted(bear_prems, reverse=True), f"{window_key} top_premium_bearish not sorted DESC"

        # Invariant: Top Bullish Hits must be sorted by contract_count DESC
        bull_hits = [item["contract_count"] for item in win["top_hits_bullish"]]
        assert bull_hits == sorted(bull_hits, reverse=True), f"{window_key} top_hits_bullish not sorted DESC"

        # Invariant: Top Bearish Hits must be sorted by contract_count DESC
        bear_hits = [item["contract_count"] for item in win["top_hits_bearish"]]
        assert bear_hits == sorted(bear_hits, reverse=True), f"{window_key} top_hits_bearish not sorted DESC"

        # Invariant: Item schema fields
        for section in ("top_premium_bullish", "top_hits_bullish", "top_premium_bearish", "top_hits_bearish"):
            for idx, item in enumerate(win[section], start=1):
                assert item["rank"] == idx
                assert item["symbol"]
                assert "formatted_premium" in item
                assert "$" in item["formatted_premium"]
                assert item["contract_count"] >= 1
                assert item["active_days"] >= 1


def test_flow_aggregate_with_as_of_date():
    """Verify querying /api/flow/aggregate with explicit as_of_date parameter."""
    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/flow/aggregate?as_of_date=2026-09-04", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["as_of_date"] == "2026-09-04"
    assert len(data["window_3d"]["top_premium_bullish"]) > 0
    assert len(data["window_1w"]["top_premium_bullish"]) > 0
    assert len(data["window_1w"]["top_premium_bearish"]) > 0

    # Verify 1W (5 sessions) tickers match expected TradingEdge week-to-date
    top_prem_1w = [item["symbol"] for item in data["window_1w"]["top_premium_bullish"]]
    assert top_prem_1w[:4] == ["SMH", "AMD", "NVDA", "MU"]

    top_hits_1w = [item["symbol"] for item in data["window_1w"]["top_hits_bullish"]]
    assert top_hits_1w[:3] == ["NVDA", "SOXL", "AMD"]

