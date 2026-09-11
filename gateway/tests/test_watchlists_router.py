import pytest
from fastapi.testclient import TestClient
import sqlalchemy as sa

from app.main import app
from app.core.auth import create_session_token
from app.core.index_validator import validate_ticker_in_indices
from app.routers.watchlists import set_custom_engine

client = TestClient(app)


@pytest.fixture
def auth_header():
    token, _ = create_session_token(expires_in_hours=6)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def setup_sqlite_db():
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=sa.pool.StaticPool,
    )
    set_custom_engine(engine)
    yield
    set_custom_engine(None)


def test_index_validator():
    # Valid tickers in major indices
    valid, indices = validate_ticker_in_indices("NVDA")
    assert valid is True
    assert "S&P 500" in indices or "Nasdaq 100" in indices

    valid, indices = validate_ticker_in_indices("SPY")
    assert valid is True
    assert "Major ETF" in indices

    valid, indices = validate_ticker_in_indices("POWL")
    assert valid is True
    assert "Russell 2000" in indices

    # Invalid tickers (micro-caps / penny stocks / fake symbols)
    valid, indices = validate_ticker_in_indices("PURR")
    assert valid is False
    assert len(indices) == 0

    valid, indices = validate_ticker_in_indices("XYZFAKE123")
    assert valid is False

    valid, indices = validate_ticker_in_indices("")
    assert valid is False


def test_watchlists_auth_rejection():
    # Missing auth header should return 401
    resp = client.get("/api/watchlists")
    assert resp.status_code == 401


def test_watchlists_get_bootstraps_default(auth_header):
    resp = client.get("/api/watchlists", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    core_wl = next((w for w in data if "core" in w["id"]), None)
    assert core_wl is not None
    assert core_wl["name"] == "Core Watchlist"
    assert len(core_wl["tickers"]) >= 1

    symbols = [t["ticker"] for t in core_wl["tickers"]]
    assert "NVDA" in symbols
    assert "SPY" in symbols


def test_create_watchlist(auth_header):
    # Empty name should fail
    resp = client.post("/api/watchlists", json={"name": "   "}, headers=auth_header)
    assert resp.status_code == 400

    # Valid name
    resp = client.post("/api/watchlists", json={"name": "Semis & AI"}, headers=auth_header)
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "Semis & AI"
    assert "semis_ai" in created["id"]
    assert created["tickers"] == []

    # Verify present in list
    resp = client.get("/api/watchlists", headers=auth_header)
    all_wl = resp.json()
    found = any(w["id"] == created["id"] for w in all_wl)
    assert found is True


def test_add_ticker_validation_and_duplicate_handling(auth_header):
    # Create watchlist
    resp = client.post("/api/watchlists", json={"name": "Test Watchlist"}, headers=auth_header)
    wl_id = resp.json()["id"]

    # 1. Add valid ticker (AMD is in S&P 500 and Nasdaq 100)
    resp = client.post(f"/api/watchlists/{wl_id}/tickers", json={"ticker": "AMD"}, headers=auth_header)
    assert resp.status_code == 201
    item = resp.json()
    assert item["ticker"] == "AMD"
    assert len(item["indices"]) > 0

    # 2. Duplicate ticker in same watchlist should return 409 Conflict
    resp = client.post(f"/api/watchlists/{wl_id}/tickers", json={"ticker": "amd"}, headers=auth_header)
    assert resp.status_code == 409

    # 3. Invalid non-index ticker should return 400 Bad Request
    resp = client.post(f"/api/watchlists/{wl_id}/tickers", json={"ticker": "PURR"}, headers=auth_header)
    assert resp.status_code == 400
    assert "not a constituent" in resp.json()["detail"].lower()

    # 4. Adding to non-existent watchlist should return 404
    resp = client.post("/api/watchlists/wl_nonexistent/tickers", json={"ticker": "AMD"}, headers=auth_header)
    assert resp.status_code == 404


def test_remove_ticker_and_delete_watchlist(auth_header):
    # Create watchlist and add a ticker
    resp = client.post("/api/watchlists", json={"name": "Delete Test"}, headers=auth_header)
    wl_id = resp.json()["id"]

    client.post(f"/api/watchlists/{wl_id}/tickers", json={"ticker": "MSFT"}, headers=auth_header)

    # Remove existing ticker
    resp = client.delete(f"/api/watchlists/{wl_id}/tickers/MSFT", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Remove non-existent ticker should return 404
    resp = client.delete(f"/api/watchlists/{wl_id}/tickers/MSFT", headers=auth_header)
    assert resp.status_code == 404

    # Delete watchlist
    resp = client.delete(f"/api/watchlists/{wl_id}", headers=auth_header)
    assert resp.status_code == 200

    # Delete non-existent watchlist should return 404
    resp = client.delete(f"/api/watchlists/{wl_id}", headers=auth_header)
    assert resp.status_code == 404
