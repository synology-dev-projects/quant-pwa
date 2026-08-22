import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "quant-gateway"
    assert "market" in data
    assert "status" in data["market"]

def test_auth_rejection_missing_header():
    response = client.get("/api/models")
    assert response.status_code == 401

def test_auth_rejection_invalid_passcode():
    response = client.get("/api/models", headers={"Authorization": "Bearer wrong-passcode"})
    assert response.status_code == 401

def test_auth_success_valid_passcode():
    valid_passcode = settings.APP_PASSCODE
    response = client.get("/api/models", headers={"Authorization": f"Bearer {valid_passcode}"})
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert len(data["models"]) >= 1

def test_chat_stream_auth_rejection_missing_header():
    response = client.post("/api/chat/stream", json={"messages": [{"role": "user", "content": "test"}]})
    assert response.status_code == 401

def test_chat_stream_auth_rejection_invalid_passcode():
    response = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "test"}]},
        headers={"Authorization": "Bearer wrong-passcode"}
    )
    assert response.status_code == 401

def test_fail_closed_when_passcode_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "APP_PASSCODE", "")
    response = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "test"}]},
        headers={"Authorization": "Bearer test-pass"}
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Server passcode unconfigured."


import re
import json
from unittest.mock import MagicMock, patch
from app.core.agent import stream_chat_response
from app.tools.registry import record_tool_metric


@pytest.mark.anyio
async def test_stream_chat_response_emits_metrics_event():
    """Verifies that stream_chat_response yields event: metrics with valid trace_id and numerical fields."""
    mock_chat = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "SPY is in Positive Gamma regime with key call wall at 600."
    mock_chat.send_message.return_value = mock_resp

    mock_client = MagicMock()
    mock_client.chats.create.return_value = mock_chat

    with patch("app.core.agent.create_genai_client", return_value=mock_client):
        messages = [{"role": "user", "content": "What is the SPY gamma?"}]
        chunks = []
        async for chunk in stream_chat_response(messages=messages, trace_id="tr-abc123"):
            chunks.append(chunk)

    full_output = "".join(chunks)
    assert "event: metrics" in full_output

    metrics_chunk = next((c for c in chunks if c.startswith("event: metrics")), None)
    assert metrics_chunk is not None

    lines = [line.strip() for line in metrics_chunk.strip().split("\n") if line.strip()]
    assert lines[0] == "event: metrics"
    assert lines[1].startswith("data: ")

    metrics_data = json.loads(lines[1][6:])
    assert metrics_data["trace_id"] == "tr-abc123"
    assert isinstance(metrics_data["tool_decision_ms"], (int, float))
    assert metrics_data["tool_decision_ms"] >= 0.0
    assert isinstance(metrics_data["tool_ms"], (int, float))
    assert metrics_data["tool_ms"] >= 0.0
    assert metrics_data["cache_status"] in ["HIT", "MISS", "COLD"]
    assert isinstance(metrics_data["retry_attempts"], int)
    assert metrics_data["retry_attempts"] >= 0
    assert isinstance(metrics_data["synthesis_ttft_ms"], (int, float))
    assert metrics_data["synthesis_ttft_ms"] >= 0.0
    assert isinstance(metrics_data["llm_ttft_ms"], (int, float))
    assert metrics_data["llm_ttft_ms"] >= 0.0
    assert isinstance(metrics_data["token_count"], int)
    assert metrics_data["token_count"] == 12
    assert isinstance(metrics_data["tok_per_sec"], (int, float))
    assert metrics_data["tok_per_sec"] >= 0.0
    assert isinstance(metrics_data["server_total_ms"], (int, float))
    assert metrics_data["server_total_ms"] > 0.0


@pytest.mark.anyio
async def test_stream_chat_response_generates_valid_trace_id_and_tool_metrics():
    """Verifies automatic 6-character trace_id generation and tool execution metrics aggregation."""
    def mock_send(prompt):
        # Simulate tool execution during chat send
        record_tool_metric(latency_ms=45.2, cache_status="HIT", retry_count=1)
        mock_resp = MagicMock()
        mock_resp.text = "AAPL gamma breakdown: Neutral positioning."
        return mock_resp

    mock_chat = MagicMock()
    mock_chat.send_message.side_effect = mock_send

    mock_client = MagicMock()
    mock_client.chats.create.return_value = mock_chat

    with patch("app.core.agent.create_genai_client", return_value=mock_client):
        messages = [{"role": "user", "content": "AAPL options"}]
        chunks = []
        async for chunk in stream_chat_response(messages=messages):
            chunks.append(chunk)

    metrics_chunk = next(c for c in chunks if c.startswith("event: metrics"))
    lines = [line.strip() for line in metrics_chunk.strip().split("\n") if line.strip()]
    metrics_data = json.loads(lines[1][6:])

    # Validate regex pattern: tr- followed by 6 hex characters
    assert re.match(r"^tr-[0-9a-fA-F]{6}$", metrics_data["trace_id"])
    assert isinstance(metrics_data["tool_decision_ms"], (int, float))
    assert metrics_data["tool_decision_ms"] >= 0.0
    assert metrics_data["tool_ms"] == 45.2
    assert metrics_data["cache_status"] == "HIT"
    assert metrics_data["retry_attempts"] == 1
    assert isinstance(metrics_data["synthesis_ttft_ms"], (int, float))
    assert metrics_data["synthesis_ttft_ms"] >= 0.0
    assert isinstance(metrics_data["llm_ttft_ms"], (int, float))
    assert metrics_data["llm_ttft_ms"] >= 0.0
    assert metrics_data["token_count"] == 5


def test_chat_stream_api_endpoint_metrics():
    """Verifies that the /api/chat/stream HTTP endpoint returns X-Trace-ID header and metrics SSE event."""
    mock_chat = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Market regime analysis: Bullish."
    mock_chat.send_message.return_value = mock_resp

    mock_client = MagicMock()
    mock_client.chats.create.return_value = mock_chat

    with patch("app.core.agent.create_genai_client", return_value=mock_client):
        valid_passcode = settings.APP_PASSCODE
        response = client.post(
            "/api/chat/stream",
            json={"messages": [{"role": "user", "content": "SPY"}]},
            headers={"Authorization": f"Bearer {valid_passcode}"}
        )
        assert response.status_code == 200
        assert "X-Trace-ID" in response.headers
        assert response.headers["X-Trace-ID"].startswith("tr-")
        assert "event: metrics" in response.text
        assert '"tool_decision_ms":' in response.text
        assert '"synthesis_ttft_ms":' in response.text
        assert '"llm_ttft_ms":' in response.text
        assert '"server_total_ms":' in response.text
        assert '"tok_per_sec":' in response.text


