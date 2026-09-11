import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import sqlalchemy as sa

from app.main import app
from app.core.auth import create_session_token
from app.core.quote_feed import get_batch_quotes, clear_quote_cache, fetch_single_quote
from app.routers.watchlists import set_custom_engine

client = TestClient(app)


@pytest.fixture
def auth_header():
    token, _ = create_session_token(expires_in_hours=6)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def setup_sqlite_db():
    clear_quote_cache()
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=sa.pool.StaticPool,
    )
    set_custom_engine(engine)
    yield
    set_custom_engine(None)
    clear_quote_cache()


MOCK_YAHOO_RESPONSE = {
    "chart": {
        "result": [
            {
                "meta": {
                    "symbol": "NVDA",
                    "regularMarketPrice": 218.50,
                    "previousClose": 215.00,
                    "regularMarketDayHigh": 220.00,
                    "regularMarketDayLow": 214.00,
                }
            }
        ]
    }
}


@pytest.mark.anyio
async def test_fetch_single_quote_success():
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_YAHOO_RESPONSE
        mock_get.return_value = mock_resp

        import httpx
        async with httpx.AsyncClient() as http_client:
            res = await fetch_single_quote(http_client, "NVDA")

        assert res is not None
        assert res["ticker"] == "NVDA"
        assert res["price"] == 218.50
        assert res["change"] == 3.50
        assert res["change_pct"] == 1.63
        assert res["prev_close"] == 215.00
        assert res["is_stale"] is False


@pytest.mark.anyio
async def test_get_batch_quotes_caching():
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_YAHOO_RESPONSE
        mock_get.return_value = mock_resp

        # Call 1: Fetches from upstream
        quotes1 = await get_batch_quotes(["NVDA"])
        assert "NVDA" in quotes1
        assert quotes1["NVDA"]["price"] == 218.50
        assert mock_get.call_count == 1

        # Call 2: Within 4-second TTL, must hit cache (no new network call)
        quotes2 = await get_batch_quotes(["NVDA"])
        assert "NVDA" in quotes2
        assert mock_get.call_count == 1  # Call count remains 1!


@pytest.mark.anyio
async def test_quotes_endpoint_auth_and_responses(auth_header):
    # 1. Unauthenticated request rejected with 401
    resp = client.get("/api/watchlists/wl_core_watchlist/quotes")
    assert resp.status_code == 401

    # 2. Non-existent watchlist returns 404
    resp = client.get("/api/watchlists/wl_does_not_exist/quotes", headers=auth_header)
    assert resp.status_code == 404

    # 3. Create a watchlist and add a ticker
    create_resp = client.post("/api/watchlists", json={"name": "Tech Quotes"}, headers=auth_header)
    assert create_resp.status_code == 201
    wl_id = create_resp.json()["id"]

    client.post(f"/api/watchlists/{wl_id}/tickers", json={"ticker": "NVDA"}, headers=auth_header)

    # 4. Fetch quotes with mock
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_YAHOO_RESPONSE
        mock_get.return_value = mock_resp

        resp = client.get(f"/api/watchlists/{wl_id}/quotes", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["watchlist_id"] == wl_id
        assert "NVDA" in data["quotes"]
        assert data["quotes"]["NVDA"]["price"] == 218.50
        assert data["quotes"]["NVDA"]["change_pct"] == 1.63
