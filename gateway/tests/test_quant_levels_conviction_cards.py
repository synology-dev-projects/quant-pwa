import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.routers.quant_levels_status import (
    compute_move_conviction,
    GammaConvictionItem,
    MarketInternalsItem,
    NetDeltaFlowItem,
    VolTermStructureItem,
    MoveConvictionContext
)


def test_compute_move_conviction_positive_gamma_contango():
    """Verify conviction scoring when SPX is in positive gamma, broad breadth, and contango."""
    quotes = {
        "^GSPC": {"ticker": "^GSPC", "price": 5700.0, "change": 25.0, "change_pct": 0.44},
        "^VIX": {"ticker": "^VIX", "price": 14.5, "change": -0.5, "change_pct": -3.33},
        "^VIX9D": {"ticker": "^VIX9D", "price": 13.2, "change": -0.8, "change_pct": -5.71},
        "RSP": {"ticker": "RSP", "price": 175.0, "change": 1.2, "change_pct": 0.69},
        "SPY": {"ticker": "SPY", "price": 570.0, "change": 2.5, "change_pct": 0.44},
        "^NYA": {"ticker": "^NYA", "price": 19500.0, "change": 110.0, "change_pct": 0.57}
    }
    gex_data = {
        "spot_price": 5700.0,
        "zero_gex_level": 5650.0,
        "net_gex": 1_850_000_000.0,
        "call_wall": 5750.0,
        "put_wall": 5600.0,
        "gamma_regime": "Long Gamma"
    }
    flow_df = pd.DataFrame([
        {"ORDER_TYPE": "CALL SWEEP ASK", "PREMIUM": 1_500_000, "IS_UNUSUAL_OI": True},
        {"ORDER_TYPE": "CALL TRADE ASK", "PREMIUM": 800_000, "IS_UNUSUAL_OI": False},
        {"ORDER_TYPE": "PUT TRADE BID", "PREMIUM": 400_000, "IS_UNUSUAL_OI": False},
    ])

    ctx = compute_move_conviction(spot_price=5700.0, quotes=quotes, gex_data=gex_data, flow_df=flow_df)

    assert isinstance(ctx, MoveConvictionContext)
    # 1. Gamma Conviction
    assert ctx.gamma.regime_type == "POSITIVE_GAMMA"
    assert "DAMPENED" in ctx.gamma.regime_label or "PIN" in ctx.gamma.regime_label
    assert ctx.gamma.flip_distance_pts == 50.0  # 5700 - 5650

    # 2. Market Internals
    assert ctx.internals.rsp_change_pct == 0.69
    assert ctx.internals.spy_change_pct == 0.44
    assert round(ctx.internals.breadth_spread, 2) == 0.25  # 0.69 - 0.44
    assert ctx.internals.breadth_regime == "BROAD_PARTICIPATION"

    # 3. Flow Net Delta
    assert ctx.flow.whale_count == 1
    assert ctx.flow.net_delta_bias == "BULLISH_FLOW"
    assert ctx.flow.aggressor_sweep_pct > 50.0

    # 4. Vol Term Structure
    assert ctx.term_structure.ratio < 1.0  # 13.2 / 14.5
    assert ctx.term_structure.term_regime == "CONTANGO"

    # Composite Verdict
    assert ctx.composite_score >= 60
    assert ctx.verdict_badge in ["HIGH CONVICTION EXPANSION", "VOL DAMPENED / STABLE DRIFT", "SOLID CONFLUENCE"]


def test_compute_move_conviction_negative_gamma_backwardation():
    """Verify conviction scoring during liquidation panic: negative gamma + backwardation."""
    quotes = {
        "^GSPC": {"ticker": "^GSPC", "price": 5600.0, "change": -60.0, "change_pct": -1.06},
        "^VIX": {"ticker": "^VIX", "price": 22.0, "change": 3.5, "change_pct": 18.9},
        "^VIX9D": {"ticker": "^VIX9D", "price": 25.5, "change": 5.2, "change_pct": 25.6},
        "RSP": {"ticker": "RSP", "price": 170.0, "change": -2.5, "change_pct": -1.45},
        "SPY": {"ticker": "SPY", "price": 560.0, "change": -6.0, "change_pct": -1.06},
        "^NYA": {"ticker": "^NYA", "price": 19000.0, "change": -300.0, "change_pct": -1.55}
    }
    gex_data = {
        "spot_price": 5600.0,
        "zero_gex_level": 5660.0,
        "net_gex": -2_100_000_000.0,
        "call_wall": 5700.0,
        "put_wall": 5550.0,
        "gamma_regime": "Short Gamma"
    }
    flow_df = pd.DataFrame([
        {"ORDER_TYPE": "PUT SWEEP ASK", "PREMIUM": 2_500_000, "IS_UNUSUAL_OI": True},
        {"ORDER_TYPE": "PUT TRADE ASK", "PREMIUM": 1_200_000, "IS_UNUSUAL_OI": True},
    ])

    ctx = compute_move_conviction(spot_price=5600.0, quotes=quotes, gex_data=gex_data, flow_df=flow_df)

    assert ctx.gamma.regime_type == "NEGATIVE_GAMMA"
    assert "ACCELERATION" in ctx.gamma.regime_label
    assert ctx.term_structure.term_regime == "BACKWARDATION"
    assert ctx.term_structure.ratio > 1.0  # 25.5 / 22.0
    assert ctx.internals.breadth_regime == "BROAD_SELLING"
    assert ctx.verdict_badge in ["HIGH ACCELERATION TREND", "LIQUIDATION / SHORT GAMMA EXPANSION"]


def test_quant_levels_endpoint_includes_conviction_context():
    """Verify that /api/quant-levels/data returns conviction_context object."""
    client = TestClient(app)
    with patch("app.routers.quant_levels_status.postgres.get_quant_levels") as mock_levels, \
         patch("app.routers.quant_levels_status.get_batch_quotes") as mock_quotes, \
         patch("app.routers.quant_levels_status.postgres.sql") as mock_sql:

        mock_sql.return_value = pd.DataFrame([{"d": "2026-09-23"}])

        mock_levels.return_value = pd.DataFrame([
            {
                "DATETIME": "2026-09-23 09:30:00",
                "TICKER": "SPX",
                "START_LVL_PRICE": 5700.0,
                "END_LVL_PRICE": None,
                "COMMENTS": "Major Pivot",
                "BUY_SELL_IND": "PIVOT",
                "WEB_LINK": None
            }
        ])
        mock_quotes.return_value = {
            "^GSPC": MagicMock(ticker="^GSPC", price=5700.0, change=10.0, change_pct=0.18, prev_close=5690.0),
            "^VIX": MagicMock(ticker="^VIX", price=15.0, change=0.2, change_pct=1.35, prev_close=14.8),
            "^TNX": MagicMock(ticker="^TNX", price=4.25, change=0.02, change_pct=0.47, prev_close=4.23),
            "^VIX9D": MagicMock(ticker="^VIX9D", price=14.2, change=0.1, change_pct=0.71, prev_close=14.1),
            "RSP": MagicMock(ticker="RSP", price=175.0, change=0.8, change_pct=0.46, prev_close=174.2),
            "SPY": MagicMock(ticker="SPY", price=570.0, change=1.0, change_pct=0.18, prev_close=569.0),
            "^NYA": MagicMock(ticker="^NYA", price=19500.0, change=80.0, change_pct=0.41, prev_close=19420.0),
        }

        resp = client.get("/api/quant-levels/data?ticker=SPX")
        assert resp.status_code == 200
        data = resp.json()

        assert "conviction_context" in data
        assert data["conviction_context"] is not None
        c_ctx = data["conviction_context"]
        assert "gamma" in c_ctx
        assert "internals" in c_ctx
        assert "flow" in c_ctx
        assert "term_structure" in c_ctx
        assert "composite_score" in c_ctx
        assert "verdict_badge" in c_ctx
