"""
gateway/tests/test_quant_levels_macro_correlation.py
Tests for SPX Quant Levels cross-asset macro correlation context (VIX and 10Y Treasury Yield).
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.routers.quant_levels_status import (
    compute_macro_correlation,
    MacroItem,
    MacroCorrelationContext,
)

client = TestClient(app)


def test_compute_macro_correlation_risk_on():
    """
    Tests that compressed VIX (<13.5) and stable 10Y yield produce a bullish risk-on reaction.
    """
    quotes = {
        "^VIX": {"ticker": "^VIX", "price": 12.80, "change": -0.40, "change_pct": -3.03, "updated_at": "2026-09-23T12:00:00Z"},
        "^TNX": {"ticker": "^TNX", "price": 4.150, "change": 0.010, "change_pct": 0.24, "updated_at": "2026-09-23T12:00:00Z"}
    }
    ctx = compute_macro_correlation(quotes, spx_price=5750.0)

    assert ctx.vix is not None
    assert ctx.vix.price == 12.80
    assert ctx.vix.sentiment == "BULLISH"
    assert "EXTREME COMPRESSION" in ctx.vix.regime_tag

    assert ctx.us10y is not None
    assert ctx.us10y.price == 4.150
    assert ctx.us10y.sentiment == "NEUTRAL"
    assert "YIELD STABLE" in ctx.us10y.regime_tag

    assert ctx.spx_reaction == "BULLISH_SUPPORTIVE"
    assert ctx.reaction_label == "RISK-ON TAILWINDS"
    assert "favorable for equity expansion" in ctx.composite_regime


def test_compute_macro_correlation_dual_headwinds():
    """
    Tests that surging VIX (>22.0 with spike) and surging 10Y yield (>5 bps) trigger cross-asset headwinds.
    """
    quotes = {
        "^VIX": {"ticker": "^VIX", "price": 24.50, "change": 2.10, "change_pct": 9.38, "updated_at": "2026-09-23T12:00:00Z"},
        "^TNX": {"ticker": "^TNX", "price": 4.380, "change": 0.080, "change_pct": 1.86, "updated_at": "2026-09-23T12:00:00Z"}
    }
    ctx = compute_macro_correlation(quotes, spx_price=5680.0)

    assert ctx.vix.sentiment == "BEARISH"
    assert "HIGH VOLATILITY" in ctx.vix.regime_tag
    assert "(SPIKING)" in ctx.vix.regime_tag

    assert ctx.us10y.sentiment == "BEARISH"
    assert "YIELD SURGING" in ctx.us10y.regime_tag

    assert ctx.spx_reaction == "BEARISH_PRESSURE"
    assert ctx.reaction_label == "CROSS-ASSET HEADWINDS"


def test_compute_macro_correlation_rate_pressure_only():
    """
    Tests that low/stable VIX with an isolated yield surge triggers rate pressure.
    """
    quotes = {
        "^VIX": {"ticker": "^VIX", "price": 15.20, "change": 0.10, "change_pct": 0.66, "updated_at": "2026-09-23T12:00:00Z"},
        "^TNX": {"ticker": "^TNX", "price": 4.450, "change": 0.070, "change_pct": 1.60, "updated_at": "2026-09-23T12:00:00Z"}
    }
    ctx = compute_macro_correlation(quotes, spx_price=5720.0)

    assert ctx.vix.sentiment == "NEUTRAL"
    assert ctx.us10y.sentiment == "BEARISH"
    assert ctx.spx_reaction == "BEARISH_PRESSURE"
    assert ctx.reaction_label == "RATE PRESSURE"


def test_compute_macro_correlation_empty_or_partial_quotes():
    """
    Tests graceful degradation when quotes are missing or offline.
    """
    ctx_empty = compute_macro_correlation({})
    assert ctx_empty.vix is None
    assert ctx_empty.us10y is None
    assert ctx_empty.spx_reaction == "NEUTRAL_CONSOLIDATION"
    assert ctx_empty.reaction_label == "BALANCED REGIME"


def test_quant_levels_endpoint_includes_macro_context():
    """
    Tests that /api/quant-levels/data enriches its response with macro_context.
    """
    mock_quotes = {
        "^GSPC": {"ticker": "^GSPC", "price": 5755.20, "change": 12.5, "change_pct": 0.22, "updated_at": "2026-09-23T12:00:00Z"},
        "^VIX": {"ticker": "^VIX", "price": 14.10, "change": -0.35, "change_pct": -2.42, "updated_at": "2026-09-23T12:00:00Z"},
        "^TNX": {"ticker": "^TNX", "price": 4.220, "change": -0.010, "change_pct": -0.24, "updated_at": "2026-09-23T12:00:00Z"}
    }

    with patch("app.routers.quant_levels_status.get_batch_quotes", new_callable=AsyncMock) as mock_get_quotes:
        mock_get_quotes.return_value = mock_quotes

        resp = client.get("/api/quant-levels/data?ticker=SPX")
        assert resp.status_code == 200
        data = resp.json()

        assert "macro_context" in data
        macro = data["macro_context"]
        assert macro is not None
        assert macro["vix"]["price"] == 14.10
        assert macro["us10y"]["price"] == 4.220
        assert macro["spx_reaction"] == "BULLISH_SUPPORTIVE"
        assert macro["reaction_label"] == "RISK-ON TAILWINDS"
