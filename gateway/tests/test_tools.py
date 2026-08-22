import pytest
from datetime import datetime
import pytz
from app.core.temporal import get_market_status, generate_temporal_system_prompt
from app.core.context import apply_sliding_window
from app.tools.registry import registry

NY_TZ = pytz.timezone("America/New_York")

def test_market_status_structure():
    status = get_market_status()
    assert "status" in status
    assert "is_live_trading" in status
    assert "current_time_ny" in status
    assert "iso_timestamp" in status

def test_market_status_regular_hours():
    # Tuesday at 11:00 AM EDT
    dt = NY_TZ.localize(datetime(2026, 8, 18, 11, 0, 0))
    status = get_market_status(dt)
    assert status["status"] == "REGULAR_HOURS"
    assert status["is_live_trading"] is True

def test_market_status_weekend():
    # Saturday at 2:00 PM EDT
    dt = NY_TZ.localize(datetime(2026, 8, 22, 14, 0, 0))
    status = get_market_status(dt)
    assert status["status"] == "WEEKEND_CLOSED"
    assert status["is_live_trading"] is False

def test_sliding_window():
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
    trimmed = apply_sliding_window(msgs, max_messages=5)
    assert len(trimmed) == 5
    assert trimmed[0]["content"] == "msg 15"
    assert trimmed[-1]["content"] == "msg 19"

def test_tool_registry():
    declarations = registry.get_all_declarations()
    assert len(declarations) >= 1
    tool_names = [d["name"] for d in declarations]
    assert "get_gexdex" in tool_names

def test_clean_image_references():
    from app.tools.gexdex_tool import _clean_image_references
    payload = {
        "ticker": "AAPL",
        "spot_price": 224.5,
        "markdown_image": "![AAPL Chart](/api/v1/gexdex/chart.png?ticker=AAPL)",
        "chart_png_url": "/api/v1/gexdex/chart.png?ticker=AAPL",
        "nested": {
            "chart_url": "http://example.com/chart.png",
            "val": 123
        }
    }
    cleaned = _clean_image_references(payload)
    assert "markdown_image" not in cleaned
    assert "chart_png_url" not in cleaned
    assert "chart_url" not in cleaned["nested"]
    assert cleaned["nested"]["val"] == 123
    assert cleaned["spot_price"] == 224.5

def test_emit_ui_events_from_payload_single():
    from app.tools.gexdex_tool import _emit_ui_events_from_payload
    from app.tools.registry import tool_ui_events_var

    events = []
    tool_ui_events_var.set(events)

    strike_dist = {
        "ticker": "SPY",
        "spot_price": 550.0,
        "strikes": [{"strike": 550.0, "call_gex": 100, "put_gex": -50}]
    }
    payload = {
        "ticker": "SPY",
        "spot_price": 550.0,
        "markdown_image": "![SPY](/chart.png)",
        "chart_png_url": "/chart.png",
        "strike_distribution": strike_dist
    }

    _emit_ui_events_from_payload(payload)

    assert "markdown_image" not in payload
    assert "chart_png_url" not in payload
    assert len(events) == 1
    assert events[0]["type"] == "tool_ui"
    assert events[0]["name"] == "get_gexdex"
    assert events[0]["payload"]["ticker"] == "SPY"

def test_emit_ui_events_from_payload_batch():
    from app.tools.gexdex_tool import _emit_ui_events_from_payload
    from app.tools.registry import tool_ui_events_var

    events = []
    tool_ui_events_var.set(events)

    payload = {
        "batch_data": {
            "AAPL": {
                "ticker": "AAPL",
                "markdown_image": "![AAPL](/chart.png)",
                "strike_distribution": {"ticker": "AAPL", "strikes": [220, 225]}
            },
            "TSLA": {
                "ticker": "TSLA",
                "chart_png_url": "/chart.png",
                "strike_distribution": {"ticker": "TSLA", "strikes": [200, 210]}
            }
        }
    }

    _emit_ui_events_from_payload(payload)

    assert "markdown_image" not in payload["batch_data"]["AAPL"]
    assert "chart_png_url" not in payload["batch_data"]["TSLA"]
    assert len(events) == 2
    emitted_tickers = [e["payload"]["ticker"] for e in events]
    assert "AAPL" in emitted_tickers
    assert "TSLA" in emitted_tickers


def test_get_gexdex_multi_ticker_timeout():
    from unittest.mock import patch, MagicMock
    from app.tools.gexdex_tool import get_gexdex, _HTTP_CLIENT
    from app.tools.registry import tool_ui_events_var

    events = []
    tool_ui_events_var.set(events)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "count": 4,
        "tickers": ["META", "AMZN", "NFLX", "GOOGL"],
        "batch_data": {
            "META": {"ticker": "META", "spot_price": 500.0, "gamma_regime": "Positive Gamma", "call_wall": 520.0, "put_wall": 480.0, "zero_gex_level": 495.0, "net_gex": 120000000.0, "net_dex": -50000000.0, "call_put_ratio": 1.5, "pin_risk_level": "LOW", "front_week_gex_pct": 35.0, "strike_distribution": {"ticker": "META", "strikes": [{"strike": 520.0, "call_gex": 50000000.0, "put_gex": -10000000.0}]}},
            "AMZN": {"ticker": "AMZN", "spot_price": 180.0, "gamma_regime": "Neutral", "call_wall": 185.0, "put_wall": 175.0, "zero_gex_level": 178.0, "net_gex": 45000000.0, "net_dex": 10000000.0, "call_put_ratio": 1.1, "pin_risk_level": "LOW", "front_week_gex_pct": 20.0, "strike_distribution": {"ticker": "AMZN", "strikes": [{"strike": 185.0, "call_gex": 20000000.0, "put_gex": -5000000.0}]}},
            "NFLX": {"ticker": "NFLX", "spot_price": 650.0, "gamma_regime": "Positive Gamma", "call_wall": 670.0, "put_wall": 630.0, "zero_gex_level": 645.0, "net_gex": 80000000.0, "net_dex": -20000000.0, "call_put_ratio": 1.8, "pin_risk_level": "MODERATE", "front_week_gex_pct": 40.0, "strike_distribution": {"ticker": "NFLX", "strikes": [{"strike": 670.0, "call_gex": 30000000.0, "put_gex": -8000000.0}]}},
            "GOOGL": {"ticker": "GOOGL", "spot_price": 170.0, "gamma_regime": "Negative Gamma", "call_wall": 175.0, "put_wall": 165.0, "zero_gex_level": 172.0, "net_gex": -30000000.0, "net_dex": -80000000.0, "call_put_ratio": 0.8, "pin_risk_level": "HIGH", "front_week_gex_pct": 55.0, "strike_distribution": {"ticker": "GOOGL", "strikes": [{"strike": 175.0, "call_gex": 10000000.0, "put_gex": -25000000.0}]}}
        }
    }

    with patch.object(_HTTP_CLIENT, "get", return_value=mock_resp) as mock_get:
        res = get_gexdex(ticker="META,AMZN,NFLX,GOOGL", force_refresh=True)

        mock_get.assert_called_once()
        assert isinstance(res, str)
        assert "[QUANTITATIVE MICROSTRUCTURE SUMMARY: META]" in res
        assert "[QUANTITATIVE MICROSTRUCTURE SUMMARY: AMZN]" in res
        assert "[QUANTITATIVE MICROSTRUCTURE SUMMARY: NFLX]" in res
        assert "[QUANTITATIVE MICROSTRUCTURE SUMMARY: GOOGL]" in res
        assert "strike_distribution" not in res
        assert len(events) == 4
        emitted_tickers = [e["payload"]["ticker"] for e in events]
        assert "META" in emitted_tickers
        assert "AMZN" in emitted_tickers
        assert "NFLX" in emitted_tickers
        assert "GOOGL" in emitted_tickers


def test_get_gexdex_single_ticker_summary_formatting():
    from unittest.mock import patch, MagicMock
    from app.tools.gexdex_tool import get_gexdex, _HTTP_CLIENT
    from app.tools.registry import tool_ui_events_var

    events = []
    tool_ui_events_var.set(events)

    strike_dist = {
        "ticker": "SPY",
        "spot_price": 580.0,
        "strikes": [
            {"strike": 590.0, "call_gex": 500000000.0, "put_gex": -50000000.0},
            {"strike": 585.0, "call_gex": 350000000.0, "put_gex": -80000000.0},
            {"strike": 570.0, "call_gex": 20000000.0, "put_gex": -450000000.0}
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "ticker": "SPY",
        "spot_price": 580.0,
        "gamma_regime": "Positive Gamma",
        "net_gex": 1500000000.0,
        "net_dex": -800000000.0,
        "call_wall": 590.0,
        "put_wall": 570.0,
        "zero_gex_level": 575.0,
        "call_put_ratio": 1.55,
        "pin_risk_level": "LOW",
        "front_week_gex_pct": 38.5,
        "strike_distribution": strike_dist
    }

    with patch.object(_HTTP_CLIENT, "get", return_value=mock_resp) as mock_get:
        res = get_gexdex(ticker="SPY", force_refresh=True)

        mock_get.assert_called_once()

        assert isinstance(res, str)
        assert "[QUANTITATIVE MICROSTRUCTURE SUMMARY: SPY]" in res
        assert "• Spot Price: $580.00 | Regime: Positive Gamma (Net GEX: +$1.50B)" in res
        assert "• Structural Walls: Call Wall $590.00 | Put Wall $570.00 | Zero GEX Flip: $575.00" in res
        assert "• Key Gamma Clusters: Calls: $590.00 (+$500.00M), $585.00 (+$350.00M), $570.00 (+$20.00M) | Puts: $570.00 (-$450.00M), $585.00 (-$80.00M), $590.00 (-$50.00M)" in res
        assert "• Market Metrics: Call/Put Ratio: 1.55 | Net DEX: -$800.00M | Pin Risk: LOW (Front-Week Concentration: 38.5%)" in res

        # Verify massive raw strike arrays are stripped from LLM return value
        assert "strike_distribution" not in res
        assert "raw_data" not in res
        assert "distribution_data" not in res

        # Verify tool_ui_events_var received the full strike distribution for HTML5 Canvas
        assert len(events) == 1
        assert events[0]["type"] == "tool_ui"
        assert events[0]["name"] == "get_gexdex"
        assert events[0]["payload"]["ticker"] == "SPY"
        assert len(events[0]["payload"]["strikes"]) == 3


def test_get_gexdex_cache_hit_emits_ui_and_returns_summary():
    from unittest.mock import patch, MagicMock
    from app.tools.gexdex_tool import get_gexdex, _GEXDEX_MEMORY_CACHE
    from app.tools.registry import tool_ui_events_var

    events = []
    tool_ui_events_var.set(events)

    strike_dist = {
        "ticker": "NVDA",
        "spot_price": 125.0,
        "strikes": [{"strike": 130.0, "call_gex": 100000000.0, "put_gex": -20000000.0}]
    }
    cached_payload = {
        "ticker": "NVDA",
        "spot_price": 125.0,
        "gamma_regime": "Positive Gamma",
        "net_gex": 300000000.0,
        "net_dex": 150000000.0,
        "call_wall": 130.0,
        "put_wall": 120.0,
        "zero_gex_level": 122.0,
        "call_put_ratio": 1.7,
        "pin_risk_level": "LOW",
        "front_week_gex_pct": 25.0,
        "strike_distribution": strike_dist
    }

    import time
    _GEXDEX_MEMORY_CACHE["NVDA:50:25"] = {
        "data": cached_payload,
        "timestamp": time.time()
    }

    res = get_gexdex(ticker="NVDA", force_refresh=False)

    assert isinstance(res, str)
    assert "[QUANTITATIVE MICROSTRUCTURE SUMMARY: NVDA]" in res
    assert "• Spot Price: $125.00 | Regime: Positive Gamma (Net GEX: +$300.00M)" in res
    assert "• Structural Walls: Call Wall $130.00 | Put Wall $120.00 | Zero GEX Flip: $122.00" in res
    assert "strike_distribution" not in res

    # Check that UI event was re-emitted on cache HIT
    assert len(events) == 1
    assert events[0]["type"] == "tool_ui"
    assert events[0]["name"] == "get_gexdex"
    assert events[0]["payload"]["ticker"] == "NVDA"


def test_get_gexdex_fallback_without_strikes():
    from app.tools.gexdex_tool import _format_single_ticker_summary

    item = {
        "ticker": "TSLA",
        "spot_price": 250.0,
        "gamma_regime": "Neutral",
        "net_gex": 0.0,
        "net_dex": -50000000.0,
        "call_wall": 260.0,
        "put_wall": 240.0,
        "zero_gex_level": 248.0,
        "call_put_ratio": 1.0,
        "pin_risk_level": "MODERATE",
        "front_week_gex_pct": 50.0
    }

    summary = _format_single_ticker_summary(item)
    assert "[QUANTITATIVE MICROSTRUCTURE SUMMARY: TSLA]" in summary
    assert "• Key Gamma Clusters: Calls: $260.00 | Puts: $240.00" in summary
    assert "• Market Metrics: Call/Put Ratio: 1.00 | Net DEX: -$50.00M | Pin Risk: MODERATE (Front-Week Concentration: 50.0%)" in summary


@pytest.mark.anyio
async def test_warm_benchmark_cache_and_memory_cache_hit():
    """Verifies that warm_benchmark_cache() pre-warms all benchmark tickers and subsequent calls result in cache HIT."""
    from unittest.mock import patch, MagicMock
    from app.tools.gexdex_tool import (
        warm_benchmark_cache,
        get_gexdex,
        BENCHMARK_WARM_TICKERS,
        _GEXDEX_MEMORY_CACHE,
        _get_cache_key,
        _HTTP_CLIENT
    )
    from app.tools.registry import tool_metrics_var

    _GEXDEX_MEMORY_CACHE.clear()

    def mock_get(url, params=None, headers=None):
        ticker = (params.get("tickers") if params else "SPY") or "SPY"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ticker": ticker,
            "spot_price": 500.0,
            "gamma_regime": "Positive Gamma",
            "net_gex": 1000000000.0,
            "net_dex": -500000000.0,
            "call_wall": 520.0,
            "put_wall": 480.0,
            "zero_gex_level": 495.0,
            "call_put_ratio": 1.5,
            "pin_risk_level": "LOW",
            "front_week_gex_pct": 30.0,
            "strike_distribution": {
                "ticker": ticker,
                "strikes": [{"strike": 500.0, "call_gex": 50000000.0, "put_gex": -20000000.0}]
            }
        }
        return mock_resp

    with patch.object(_HTTP_CLIENT, "get", side_effect=mock_get) as mock_http_get:
        warmed_count = await warm_benchmark_cache(force_refresh=True)

        assert warmed_count == len(BENCHMARK_WARM_TICKERS)
        assert len(BENCHMARK_WARM_TICKERS) == 20

        # Verify all benchmark tickers are populated in _GEXDEX_MEMORY_CACHE
        for sym in BENCHMARK_WARM_TICKERS:
            cache_key = _get_cache_key(sym, 50, 25)
            assert cache_key in _GEXDEX_MEMORY_CACHE
            assert _GEXDEX_MEMORY_CACHE[cache_key]["data"]["ticker"] == sym

        # Verify that subsequent get_gexdex calls hit the in-memory cache and record cache_status == 'HIT'
        mock_http_get.reset_mock()
        metrics = {}
        tool_metrics_var.set(metrics)

        spy_summary = get_gexdex(ticker="SPY", force_refresh=False)
        assert "[QUANTITATIVE MICROSTRUCTURE SUMMARY: SPY]" in spy_summary
        mock_http_get.assert_not_called()
        assert metrics.get("cache_status") == "HIT"


def test_is_market_warmer_window():
    """Verifies that is_market_warmer_window correctly identifies Mon-Fri 08:30 - 16:15 ET."""
    from app.tools.gexdex_tool import is_market_warmer_window
    import pytz
    from datetime import datetime

    ny = pytz.timezone("America/New_York")

    # Tuesday 10:00 AM ET (regular hours) -> True
    dt_open = ny.localize(datetime(2026, 8, 18, 10, 0, 0))
    assert is_market_warmer_window(dt_open) is True

    # Tuesday 08:30 AM ET (window start boundary) -> True
    dt_start = ny.localize(datetime(2026, 8, 18, 8, 30, 0))
    assert is_market_warmer_window(dt_start) is True

    # Tuesday 16:15 PM ET (window end boundary) -> True
    dt_end = ny.localize(datetime(2026, 8, 18, 16, 15, 0))
    assert is_market_warmer_window(dt_end) is True

    # Tuesday 08:29 AM ET (before window) -> False
    dt_early = ny.localize(datetime(2026, 8, 18, 8, 29, 59))
    assert is_market_warmer_window(dt_early) is False

    # Tuesday 16:16 PM ET (after window) -> False
    dt_late = ny.localize(datetime(2026, 8, 18, 16, 16, 0))
    assert is_market_warmer_window(dt_late) is False

    # Saturday 12:00 PM ET (weekend) -> False
    dt_weekend = ny.localize(datetime(2026, 8, 22, 12, 0, 0))
    assert is_market_warmer_window(dt_weekend) is False

    # Sunday 09:00 AM ET (weekend) -> False
    dt_sunday = ny.localize(datetime(2026, 8, 23, 9, 0, 0))
    assert is_market_warmer_window(dt_sunday) is False


@pytest.mark.anyio
async def test_run_cache_warmer_loop_cancellation():
    """Verifies that run_cache_warmer_loop runs and cancels gracefully."""
    import asyncio
    from unittest.mock import patch, AsyncMock
    from app.tools.gexdex_tool import run_cache_warmer_loop

    with patch("app.tools.gexdex_tool.warm_benchmark_cache", new_callable=AsyncMock) as mock_warm:
        task = asyncio.create_task(run_cache_warmer_loop(interval_seconds=100))
        await asyncio.sleep(0.01)
        task.cancel()
        await task
        assert task.cancelled() or task.done()



