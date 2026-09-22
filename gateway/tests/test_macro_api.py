"""
Unit and integration tests for Macro Events Cards and RAG context Gateway endpoints.
"""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_macro_events_cards_mocked():
    fake_events = [
        {
            "event_id": "test_id_1",
            "event_timestamp": "2026-09-24T12:30:00+00:00",
            "country": "USD",
            "title": "Unemployment Claims",
            "impact_tier": "Medium",
            "forecast": "201K",
            "previous": "196K",
            "actual": None,
            "synthetic_summary": "Macroeconomic Event: [USD] Unemployment Claims",
            "status": "UPCOMING",
            "similarity_score": 0.85
        }
    ]

    with patch("common_lib.economic_events.retrieval.retrieve_relevant_events") as mock_ret:
        with patch("common_lib.economic_events.sensitivities.get_or_compute_sensitivity") as mock_sens:
            mock_ret.return_value = fake_events
            mock_sens.return_value = {"beta_rates": -0.1}
            response = client.get("/api/economic-events/macro?ticker=SPY")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["ticker"] == "SPY"
    assert data["country"] == "USD"
    assert data["count"] == 1
    card = data["events"][0]
    assert card["title"] == "Unemployment Claims"
    assert card["impact_tier"] == "Medium"
    assert "countdown_seconds" in card


def test_get_rag_context_block_mocked():
    fake_events = [
        {
            "event_id": "test_id_fomc",
            "event_timestamp": "2026-09-23T18:00:00+00:00",
            "country": "USD",
            "title": "FOMC Rate Decision",
            "impact_tier": "High",
            "forecast": "5.25%",
            "previous": "5.50%",
            "actual": None,
            "synthetic_summary": "FOMC Rate Decision",
            "status": "UPCOMING"
        }
    ]

    with patch("common_lib.economic_events.retrieval.retrieve_relevant_events") as mock_ret:
        mock_ret.return_value = fake_events
        response = client.get("/api/economic-events/rag-context?ticker=SOFI")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["ticker"] == "SOFI"
    assert data["count"] == 1
    assert "FOMC Rate Decision" in data["context_block"]


def test_synthesis_includes_macro_catalysts():
    from app.core.synthesis import synthesis_registry
    point_ids = [p.point_id for p in synthesis_registry.points]
    assert "macro_catalysts" in point_ids

    macro_point = next(p for p in synthesis_registry.points if p.point_id == "macro_catalysts")
    det_output = macro_point.generate_deterministic("SPY", {"events": []})
    assert "Macro Catalysts" in det_output
    assert "NONE PENDING" in det_output

def test_get_sensitivity_profile_mocked():
    fake_profile = {
        "ticker": "SPY",
        "beta_rates": -0.15,
        "beta_oil": 0.05,
        "beta_market": 1.0,
        "thematic_tags": ["high-beta"],
        "primary_catalysts": ["broad market sentiment"],
        "query_expansion": "SPY macro catalysts, broad market sentiment",
        "last_calculated_at": "2026-09-24T12:30:00+00:00"
    }

    with patch("common_lib.economic_events.sensitivities.get_or_compute_sensitivity") as mock_get:
        mock_get.return_value = fake_profile
        response = client.get("/api/economic-events/sensitivity?ticker=SPY")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["ticker"] == "SPY"
    prof = data["sensitivity_profile"]
    assert prof["beta_rates"] == -0.15
    assert "high-beta" in prof["thematic_tags"]
