import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.auth import create_session_token
from app.routers.cockpit import (
    CockpitRequest,
    _calculate_cockpit_metrics,
    _build_synthesis_prompt,
    _generate_deterministic_synthesis
)

client = TestClient(app)


@pytest.fixture
def auth_header():
    token, _ = create_session_token(expires_in_hours=6)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_flow_df():
    return pd.DataFrame([
        {
            "FLOW_ID": "1",
            "TRADE_DATE": "2026-08-28",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 135.0,
            "STRIKE_OTM_PCT": 3.8,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 15000,
            "IS_UNUSUAL_OI": 1,
            "PREMIUM": 1500000.0,
            "NET_SCORE": 1.5,
            "CREATED_AT": "2026-08-28 14:30:00"
        },
        {
            "FLOW_ID": "2",
            "TRADE_DATE": "2026-08-27",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 140.0,
            "STRIKE_OTM_PCT": 7.6,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 8000,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 800000.0,
            "NET_SCORE": 1.0,
            "CREATED_AT": "2026-08-27 11:15:00"
        },
        {
            "FLOW_ID": "3",
            "TRADE_DATE": "2026-08-26",
            "SYMBOL": "NVDA",
            "ORDER_TYPE": "BUY_PUT",
            "STRIKE_PRICE": 120.0,
            "STRIKE_OTM_PCT": -7.6,
            "EXPIRATION_DATE": "2026-09-18",
            "OPEN_INTEREST": 4500,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 200000.0,
            "NET_SCORE": -0.8,
            "CREATED_AT": "2026-08-26 10:00:00"
        }
    ])


@pytest.fixture
def mock_gex_data():
    return {
        "ticker": "NVDA",
        "spot_price": 130.0,
        "zero_gex_level": 126.5,
        "call_wall": 140.0,
        "put_wall": 120.0,
        "net_gex": 4500000.0,
        "net_dex": 12000000.0,
        "gamma_regime": "Positive (Long Gamma / Volatility Dampening)",
        "expected_range_low": 125.0,
        "expected_range_high": 135.0,
        "expected_move_dollars": 5.0,
        "strike_distribution": {
            "strikes": [{"strike": 130.0, "net_gex": 500000.0}]
        }
    }


def test_cockpit_request_model():
    req = CockpitRequest(ticker="  nvda  ")
    assert req.ticker == "  nvda  "

    with pytest.raises(Exception):
        CockpitRequest()


def test_calculate_cockpit_metrics_bullish(mock_gex_data, mock_flow_df):
    metrics = _calculate_cockpit_metrics(mock_gex_data, mock_flow_df)
    assert metrics["spot_price"] == 130.0
    assert metrics["zero_gamma_flip"] == 126.5
    assert metrics["call_wall"] == 140.0
    assert metrics["put_wall"] == 120.0
    assert metrics["total_30d_flow_volume"] == 2500000.0
    assert metrics["call_flow"] == 2300000.0
    assert metrics["put_flow"] == 200000.0
    assert metrics["call_pct"] == 92.0
    assert metrics["put_pct"] == 8.0
    assert metrics["whale_count"] == 1  # 1 print >= $1M
    assert metrics["unusual_oi_count"] == 1  # 1 print with IS_UNUSUAL_OI=1
    assert metrics["confluence_bias"] == "BULLISH CONFLUENCE"


def test_calculate_cockpit_metrics_bearish():
    bearish_gex = {
        "spot_price": 120.0,
        "zero_gex_level": 125.0,
        "call_wall": 130.0,
        "put_wall": 110.0,
        "net_gex": -3000000.0,
        "net_dex": -8000000.0,
        "gamma_regime": "Negative (Short Gamma / Volatility Acceleration)"
    }
    bearish_flow = pd.DataFrame([
        {
            "ORDER_TYPE": "BUY_PUT",
            "PREMIUM": 2000000.0,
            "IS_UNUSUAL_OI": 1
        },
        {
            "ORDER_TYPE": "BUY_CALL",
            "PREMIUM": 500000.0,
            "IS_UNUSUAL_OI": 0
        }
    ])
    metrics = _calculate_cockpit_metrics(bearish_gex, bearish_flow)
    assert metrics["call_pct"] == 20.0
    assert metrics["put_pct"] == 80.0
    assert metrics["whale_count"] == 1
    assert metrics["confluence_bias"] == "BEARISH CONFLUENCE"


def test_calculate_cockpit_metrics_neutral_pin():
    pin_gex = {
        "spot_price": 100.0,
        "zero_gex_level": 100.0,
        "call_wall": 105.0,
        "put_wall": 95.0,
        "net_gex": 100000.0,
        "net_dex": 20000.0,
        "gamma_regime": "Neutral"
    }
    balanced_flow = pd.DataFrame([
        {"ORDER_TYPE": "BUY_PUT", "PREMIUM": 500000.0, "IS_UNUSUAL_OI": 0},
        {"ORDER_TYPE": "BUY_CALL", "PREMIUM": 500000.0, "IS_UNUSUAL_OI": 0}
    ])
    metrics = _calculate_cockpit_metrics(pin_gex, balanced_flow)
    assert metrics["call_pct"] == 50.0
    assert metrics["put_pct"] == 50.0
    assert metrics["confluence_bias"] == "NEUTRAL PIN"


def test_cockpit_data_auth_rejection():
    # 1. Missing header
    res = client.post("/api/cockpit/data", json={"ticker": "NVDA"})
    assert res.status_code == 401

    # 2. Invalid Bearer token
    res = client.post("/api/cockpit/data", json={"ticker": "NVDA"}, headers={"Authorization": "Bearer bad-token"})
    assert res.status_code == 401


def test_cockpit_data_success(auth_header, mock_gex_data, mock_flow_df):
    with patch("app.routers.cockpit.get_strike_distribution") as mock_gex, \
         patch("app.routers.cockpit._fetch_postgres_flow_sync") as mock_flow:
        mock_gex.return_value = mock_gex_data
        mock_flow.return_value = mock_flow_df

        response = client.post(
            "/api/cockpit/data",
            json={"ticker": " $nvda "},
            headers=auth_header
        )
        assert response.status_code == 200
        data = response.json()

        assert data["ticker"] == "NVDA"
        assert data["status"] == "ok"
        assert "gex" in data
        assert data["gex"]["spot_price"] == 130.0
        assert "flow" in data
        assert data["flow"]["total_count"] == 3
        assert len(data["flow"]["records"]) == 3

        metrics = data["metrics"]
        assert metrics["spot_price"] == 130.0
        assert metrics["zero_gamma_flip"] == 126.5
        assert metrics["call_wall"] == 140.0
        assert metrics["put_wall"] == 120.0
        assert metrics["confluence_bias"] == "BULLISH CONFLUENCE"
        assert metrics["whale_count"] == 1
        assert metrics["unusual_oi_count"] == 1


def test_cockpit_data_empty_ticker_validation(auth_header):
    response = client.post(
        "/api/cockpit/data",
        json={"ticker": "   "},
        headers=auth_header
    )
    assert response.status_code == 400
    assert "Ticker symbol cannot be empty" in response.json()["detail"]


def test_cockpit_data_fault_tolerance(auth_header):
    with patch("app.routers.cockpit.get_strike_distribution") as mock_gex, \
         patch("app.routers.cockpit._fetch_postgres_flow_sync") as mock_flow:
        # Simulate GEX failure and Postgres DB down
        mock_gex.side_effect = Exception("TradingEdge circuit trip")
        mock_flow.side_effect = Exception("Postgres connection timeout")

        response = client.post(
            "/api/cockpit/data",
            json={"ticker": "AAPL"},
            headers=auth_header
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["status"] == "ok"
        assert data["flow"]["total_count"] == 0
        assert data["metrics"]["total_30d_flow_volume"] == 0.0
        assert data["metrics"]["confluence_bias"] == "NEUTRAL PIN"


def test_cockpit_synthesis_stream_auth_rejection():
    res = client.post("/api/cockpit/synthesis/stream", json={"ticker": "NVDA"})
    assert res.status_code == 401


def test_cockpit_synthesis_stream_deterministic_fallback(auth_header, mock_gex_data, mock_flow_df, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    with patch("app.routers.cockpit.get_strike_distribution") as mock_gex, \
         patch("app.routers.cockpit._fetch_postgres_flow_sync") as mock_flow:
        mock_gex.return_value = mock_gex_data
        mock_flow.return_value = mock_flow_df

        response = client.post(
            "/api/cockpit/synthesis/stream",
            json={"ticker": "NVDA"},
            headers=auth_header
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        body = response.text
        assert "data: " in body
        assert "[DONE]" in body
        
        assembled_text = "".join(
            json.loads(line[6:])["content"]
            for line in body.splitlines()
            if line.startswith("data: {") and "content" in json.loads(line[6:])
        )
        assert "Core Confluence Thesis" in assembled_text
        assert "Microstructure Alignment" in assembled_text
        assert "Tactical Action Playbook" in assembled_text


def test_cockpit_synthesis_stream_with_gemini(auth_header, mock_gex_data, mock_flow_df, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-gemini-key")

    mock_chunk1 = MagicMock()
    mock_chunk1.text = "### 1. Core Confluence Thesis\nNVDA displays strong bullish gamma confluence. "
    mock_chunk2 = MagicMock()
    mock_chunk2.text = "### 2. Microstructure Alignment\nWhale sweeps align with $140 Call Wall. "
    mock_chunk3 = MagicMock()
    mock_chunk3.text = "### 3. Tactical Action Playbook\nBreakout trigger above $140.00."

    async def fake_async_stream(*args, **kwargs):
        for chk in [mock_chunk1, mock_chunk2, mock_chunk3]:
            yield chk

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=fake_async_stream())

    with patch("app.routers.cockpit.get_strike_distribution") as mock_gex, \
         patch("app.routers.cockpit._fetch_postgres_flow_sync") as mock_flow, \
         patch("google.genai.Client", return_value=mock_client):
        mock_gex.return_value = mock_gex_data
        mock_flow.return_value = mock_flow_df

        response = client.post(
            "/api/cockpit/synthesis/stream",
            json={"ticker": "NVDA"},
            headers=auth_header
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        body = response.text
        assert "data: " in body
        assert "[DONE]" in body
        
        assembled_text = "".join(
            json.loads(line[6:])["content"]
            for line in body.splitlines()
            if line.startswith("data: {") and "content" in json.loads(line[6:])
        )
        assert "Core Confluence Thesis" in assembled_text
        assert "Microstructure Alignment" in assembled_text
        assert "Tactical Action Playbook" in assembled_text


def test_stream_cockpit_synthesis_with_precomputed_payload(auth_header, mock_gex_data, mock_flow_df):
    mock_chunk = MagicMock()
    mock_chunk.text = "Precomputed stream token."

    async def fake_async_stream(*args, **kwargs):
        yield mock_chunk

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=fake_async_stream())

    metrics = _calculate_cockpit_metrics(mock_gex_data, mock_flow_df)
    precomputed_payload = {
        "metrics": metrics,
        "gex": mock_gex_data,
        "flow": {
            "records": mock_flow_df.to_dict(orient="records"),
            "total_count": 3
        }
    }

    with patch("app.routers.cockpit.get_strike_distribution") as mock_gex, \
         patch("app.routers.cockpit._fetch_postgres_flow_sync") as mock_flow, \
         patch("google.genai.Client", return_value=mock_client):

        response = client.post(
            "/api/cockpit/synthesis/stream",
            json={"ticker": "NVDA", "payload": precomputed_payload},
            headers=auth_header
        )
        assert response.status_code == 200
        # GEX calculation and Postgres fetch should NOT have been called
        mock_gex.assert_not_called()
        mock_flow.assert_not_called()
        assert "Precomputed stream token." in response.text

