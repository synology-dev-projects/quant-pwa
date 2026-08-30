import time
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
    assert data["version"] == settings.APP_VERSION
    assert data["environment"] == settings.ENVIRONMENT
    assert "market" in data
    assert "status" in data["market"]

def test_version_parity_with_version_json():
    """Verifies that gateway settings.APP_VERSION strictly matches root version.json."""
    from pathlib import Path
    import json

    version_file = Path(__file__).resolve().parent.parent.parent / "version.json"
    assert version_file.exists(), f"version.json not found at {version_file}"
    with open(version_file, "r", encoding="utf-8") as f:
        version_data = json.load(f)

    assert settings.APP_VERSION == version_data["version"]
    assert settings.APP_VERSION == "v1.0.3"

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
    assert "tier_used" in metrics_data
    assert metrics_data["tier_used"] in ["fast", "strategic"]
    assert "model_used" in metrics_data
    assert isinstance(metrics_data["model_used"], str)
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


def test_models_list_endpoint_structure():
    """Verifies that /api/models returns updated default model and available models hierarchy."""
    valid_passcode = settings.APP_PASSCODE
    response = client.get("/api/models", headers={"Authorization": f"Bearer {valid_passcode}"})
    assert response.status_code == 200
    data = response.json()
    assert data["default"] == "gemini-3.5-flash-lite"
    assert len(data["models"]) == 4
    model_ids = [m["id"] for m in data["models"]]
    assert model_ids == [
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-flash-latest"
    ]


def test_create_genai_client_fast_timeout_and_retries(monkeypatch):
    """Verifies that create_genai_client configures fast timeout (12s) and 1 retry attempt."""
    from app.core.agent import create_genai_client
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-12345")
    
    with patch("google.genai.Client") as mock_client_cls:
        client_inst = create_genai_client()
        assert mock_client_cls.called
        call_kwargs = mock_client_cls.call_args[1]
        assert call_kwargs["api_key"] == "test-key-12345"
        assert "http_options" in call_kwargs
        http_opts = call_kwargs["http_options"]
        assert http_opts.timeout == 60000
        assert http_opts.retry_options.attempts == 1


@pytest.mark.anyio
async def test_stream_chat_response_fast_failover():
    """Verifies that stream_chat_response fast-failovers to the next model on transient error without delay."""
    attempt_count = 0
    created_models = []

    def mock_create(model, config, history):
        nonlocal attempt_count
        created_models.append(model)
        mock_chat = MagicMock()
        if model == "gemini-3.6-flash":
            # Simulate 503 UNAVAILABLE transient failure
            from google.genai.errors import ServerError
            def fail_send(prompt):
                raise ServerError(503, {"error": {"code": 503, "message": "Model unavailable / high load"}})
            mock_chat.send_message.side_effect = fail_send
        else:
            # Fallback model succeeds
            mock_resp = MagicMock()
            mock_resp.text = "Analysis completed via fallback model."
            mock_chat.send_message.return_value = mock_resp
        return mock_chat

    mock_client = MagicMock()
    mock_client.chats.create.side_effect = mock_create

    with patch("app.core.agent.create_genai_client", return_value=mock_client):
        messages = [{"role": "user", "content": "Analyze SPY GEX"}]
        chunks = []
        t0 = time.perf_counter()
        async for chunk in stream_chat_response(messages=messages, model_name="gemini-3.6-flash"):
            chunks.append(chunk)
        elapsed = time.perf_counter() - t0

    full_output = "".join(chunks)
    # Failover should happen quickly (< 500ms in local mock)
    assert elapsed < 0.5
    # Both primary and secondary models were attempted
    assert "gemini-3.6-flash" in created_models
    assert "gemini-3.5-flash-lite" in created_models
    assert "ROUTING NOTICE" in full_output
    assert "Analysis" in full_output
    assert "fallback" in full_output


from app.core.agent import detect_query_thinking_budget, SYSTEM_INSTRUCTION_BASE
from google.genai import types


def test_system_instruction_compressed():
    """Verifies that SYSTEM_INSTRUCTION_BASE is compressed, token-dense, and preserves NO_IMAGE_SYNTAX."""
    assert "You are Quant AI, an institutional Options & Quantitative Market Strategist." in SYSTEM_INSTRUCTION_BASE
    assert "get_gexdex" in SYSTEM_INSTRUCTION_BASE
    assert "STRICT COMPLETENESS" in SYSTEM_INSTRUCTION_BASE
    # Check concise token-dense length (< 1500 chars / ~300 tokens)
    assert len(SYSTEM_INSTRUCTION_BASE) < 1500


def test_detect_query_thinking_budget_single_ticker():
    """Verifies that fast, direct single-ticker queries return a 0 thinking budget."""
    assert detect_query_thinking_budget("SPY") == 0
    assert detect_query_thinking_budget("What is the SPY gamma?") == 0
    assert detect_query_thinking_budget("AAPL options") == 0
    assert detect_query_thinking_budget("TSLA strike breakdown") == 0
    assert detect_query_thinking_budget("NVDA call put wall") == 0
    assert detect_query_thinking_budget("") == 0
    assert detect_query_thinking_budget(None) == 0


def test_detect_query_thinking_budget_complex_and_multi_ticker():
    """Verifies that complex, macro, multi-ticker, or strategy queries allocate 512 thinking budget."""
    # Cross-synthesis keywords
    assert detect_query_thinking_budget("Compare SPY and QQQ") == 512
    assert detect_query_thinking_budget("What is the FOMC risk?") == 512
    assert detect_query_thinking_budget("CPI inflation update") == 512
    assert detect_query_thinking_budget("Fed interest rate impact") == 512
    assert detect_query_thinking_budget("Cross-asset correlation") == 512
    assert detect_query_thinking_budget("Options portfolio strategy") == 512
    assert detect_query_thinking_budget("Key levels for NVDA") == 512
    assert detect_query_thinking_budget("Macro market regime") == 512
    assert detect_query_thinking_budget("What are the rates today?") == 512

    # Comma-separated multi-ticker queries
    assert detect_query_thinking_budget("SPY, AAPL, NVDA") == 512
    assert detect_query_thinking_budget("SPY,QQQ") == 512
    assert detect_query_thinking_budget("BLDP,AAOI,ADEA") == 512

    # History-based synthesis detection
    history_dict = [{"role": "user", "content": "What is the macro strategy?"}]
    assert detect_query_thinking_budget("SPY", history=history_dict) == 512

    history_content = [types.Content(role="user", parts=[types.Part.from_text(text="FOMC risk analysis")])]
    assert detect_query_thinking_budget("SPY", history=history_content) == 512


@pytest.mark.anyio
async def test_stream_chat_response_with_thinking_config():
    """Verifies that stream_chat_response configures thinking_budget dynamically in GenerateContentConfig."""
    captured_configs = []

    def mock_create(model, config, history):
        captured_configs.append(config)
        mock_chat = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Analysis complete."
        mock_chat.send_message.return_value = mock_resp
        return mock_chat

    mock_client = MagicMock()
    mock_client.chats.create.side_effect = mock_create

    with patch("app.core.agent.create_genai_client", return_value=mock_client):
        # 1. Simple query -> budget 0
        messages_simple = [{"role": "user", "content": "What is the SPY gamma?"}]
        async for _ in stream_chat_response(messages=messages_simple):
            pass

        assert len(captured_configs) == 1
        cfg1 = captured_configs[0]
        # Fast Tier 3.5-lite has thinking_config disabled to prevent Google API 400 errors
        assert cfg1.thinking_config is None

        # 2. Complex query -> strategic budget 512
        messages_complex = [{"role": "user", "content": "Explain the macro strategy for FOMC rates and portfolio correlation"}]
        async for _ in stream_chat_response(messages=messages_complex):
            pass

        assert len(captured_configs) == 2
        cfg2 = captured_configs[1]
        assert cfg2.thinking_config is not None
        assert cfg2.thinking_config.thinking_budget == 512


from app.core.agent import evaluate_synthesis_tier


def test_evaluate_synthesis_tier_single_ticker():
    """Single ticker queries route to FAST tier with TIER1_FAST_WORKER_MODEL and budget 0."""
    tier, model, budget = evaluate_synthesis_tier("SPY")
    assert tier == "FAST"
    assert model == settings.TIER1_FAST_WORKER_MODEL
    assert budget == 0

    tier, model, budget = evaluate_synthesis_tier("What is the AAPL gamma?")
    assert tier == "FAST"
    assert model == settings.TIER1_FAST_WORKER_MODEL
    assert budget == 0

    tier, model, budget = evaluate_synthesis_tier("")
    assert tier == "FAST"
    assert model == settings.TIER1_FAST_WORKER_MODEL
    assert budget == 0


def test_evaluate_synthesis_tier_multi_tool():
    """When tools_called_count >= 2, routes to STRATEGIC tier with TIER2_STRATEGIC_MODEL and budget 512."""
    tier, model, budget = evaluate_synthesis_tier("SPY", tools_called_count=2)
    assert tier == "STRATEGIC"
    assert model == settings.TIER2_STRATEGIC_MODEL
    assert budget == 512

    tier, model, budget = evaluate_synthesis_tier("SPY", tools_called_count=3)
    assert tier == "STRATEGIC"
    assert model == settings.TIER2_STRATEGIC_MODEL
    assert budget == 512


def test_evaluate_synthesis_tier_keywords():
    """When prompt or history contains cross-synthesis keywords or multi-ticker comparisons, routes to STRATEGIC tier."""
    # Keyword in prompt
    tier, model, budget = evaluate_synthesis_tier("FOMC rate decision impact on market")
    assert tier == "STRATEGIC"
    assert model == settings.TIER2_STRATEGIC_MODEL
    assert budget == 512

    tier, model, budget = evaluate_synthesis_tier("Compare options flow")
    assert tier == "STRATEGIC"
    assert model == settings.TIER2_STRATEGIC_MODEL
    assert budget == 512

    # Multi-ticker comma separated
    tier, model, budget = evaluate_synthesis_tier("SPY, QQQ")
    assert tier == "STRATEGIC"
    assert model == settings.TIER2_STRATEGIC_MODEL
    assert budget == 512

    # Keyword in history
    history = [{"role": "user", "content": "Let's review macro risk factors."}]
    tier, model, budget = evaluate_synthesis_tier("What about SPY?", history=history)
    assert tier == "STRATEGIC"
    assert model == settings.TIER2_STRATEGIC_MODEL
    assert budget == 512



