import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token
from app.core.flow_synthesis import (
    flow_synthesis_registry,
    NotableFlowPoint,
    FlowSynthesisRegistry
)

client = TestClient(app)


@pytest.fixture
def auth_header():
    token, _ = create_session_token(expires_in_hours=6)
    return {"Authorization": f"Bearer {token}"}


def test_notable_flow_point_extraction_and_deterministic():
    point = NotableFlowPoint()
    assert point.point_id == "notable_flow"
    assert point.title == "Notable Flow"

    # Test features with mock data
    mock_features = {
        "latest_date": "2026-08-28",
        "top_all_time_prints": [
            {
                "symbol": "NVDA",
                "order_type": "BUY_CALL",
                "strike": 135.0,
                "premium": 15500000.0,
                "formatted_premium": "$15.5M",
                "rank": 2,
                "expiration_date": "2026-09-18"
            }
        ],
        "deep_otm_prints": [
            {
                "symbol": "TSLA",
                "order_type": "BUY_CALL",
                "strike": 300.0,
                "otm_pct": 22.5,
                "dte": 14,
                "premium": 2500000.0,
                "formatted_premium": "$2.5M"
            }
        ],
        "top_whale_print": None
    }

    # 1. Deterministic generation check
    deterministic_out = point.generate_deterministic(mock_features)
    assert "• **Notable Flow**:" in deterministic_out
    assert "• **TOP PREMIUM**:" in deterministic_out
    assert "NVDA $15.5M PREMIUM (2nd)" in deterministic_out
    assert "• **NOTABLE OTM**:" in deterministic_out
    assert "TSLA" in deterministic_out
    assert "exp 2 weeks" in deterministic_out

    # 2. Prompt instruction check
    instruction = point.get_prompt_instruction(mock_features)
    assert "• **Notable Flow**:" in instruction
    assert "TOP PREMIUM" in instruction
    assert "NVDA $15.5M PREMIUM (2nd)" in instruction
    assert "NOTABLE OTM" in instruction

    prompt = flow_synthesis_registry.build_synthesis_prompt("2026-08-28", {"notable_flow": mock_features})
    assert "CRITICAL FORMAT REQUIREMENT" in prompt
    assert "TELEGRAPHIC / ZERO ADJECTIVES" in prompt
    assert "TOP PREMIUM" in prompt


def test_notable_flow_point_empty_fallback_none_found():
    point = NotableFlowPoint()
    mock_features = {
        "latest_date": "2026-08-28",
        "top_all_time_prints": [],
        "deep_otm_prints": []
    }

    deterministic_out = point.generate_deterministic(mock_features)
    assert "• **Notable Flow**:" in deterministic_out
    assert "• **TOP PREMIUM**:" in deterministic_out
    assert "- NONE FOUND" in deterministic_out
    assert "• **NOTABLE OTM**:" in deterministic_out


def test_flow_synthesis_registry_expandability():
    registry = FlowSynthesisRegistry()
    initial_count = len(registry.get_points())
    assert initial_count == 1

    # Create dummy custom point
    class CustomSectorPoint(NotableFlowPoint):
        def __init__(self):
            super().__init__()
            self.point_id = "sector_rotation"
            self.title = "Sector Flow Rotation"

        def generate_deterministic(self, features):
            return "• **Sector Flow Rotation**: Tech outflows matched by Financial inflows."

    custom_pt = CustomSectorPoint()
    registry.register(custom_pt)
    assert len(registry.get_points()) == initial_count + 1

    prompt = registry.build_synthesis_prompt("2026-08-28", {})
    assert "### Market Flow Snapshot" in prompt

    det = registry.generate_deterministic_synthesis({})
    assert "### Market Flow Snapshot" in det
    assert "• **Sector Flow Rotation**:" in det

    registry.unregister("sector_rotation")
    assert len(registry.get_points()) == initial_count


def test_flow_synthesis_stream_auth_rejection():
    res = client.post("/api/flow/synthesis/stream")
    assert res.status_code == 401


def test_flow_synthesis_stream_deterministic_fallback(auth_header, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    # Mock DB extraction to return a clean feature dict
    mock_features = {
        "notable_flow": {
            "latest_date": "2026-08-28",
            "top_all_time_prints": [
                {
                    "symbol": "NVDA",
                    "order_type": "BUY_CALL",
                    "strike": 135.0,
                    "premium": 15500000.0,
                    "formatted_premium": "$15.5M",
                    "rank": 1,
                    "expiration_date": "2026-09-18"
                }
            ],
            "deep_otm_prints": [],
            "top_whale_print": None
        }
    }

    with patch.object(flow_synthesis_registry, "extract_all_features", return_value=mock_features):
        res = client.post("/api/flow/synthesis/stream", headers=auth_header)
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

        body = res.text
        assert "data: " in body
        assert "[DONE]" in body
        
        import json
        assembled_text = "".join(
            json.loads(line[6:])["content"]
            for line in body.splitlines()
            if line.startswith("data: {") and "content" in json.loads(line[6:])
        )
        assert "Market Flow Snapshot" in assembled_text
        assert "Notable Flow" in assembled_text
        assert "NVDA $15.5M PREMIUM (1st)" in assembled_text
        assert "NONE FOUND" in assembled_text
