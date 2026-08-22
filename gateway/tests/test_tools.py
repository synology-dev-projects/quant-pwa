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
    from app.tools.gexdex_tool import get_gexdex

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "count": 4,
        "tickers": ["META", "AMZN", "NFLX", "GOOGL"],
        "batch_data": {
            "META": {"ticker": "META", "spot_price": 500.0},
            "AMZN": {"ticker": "AMZN", "spot_price": 180.0},
            "NFLX": {"ticker": "NFLX", "spot_price": 650.0},
            "GOOGL": {"ticker": "GOOGL", "spot_price": 170.0}
        }
    }

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        res = get_gexdex(ticker="META,AMZN,NFLX,GOOGL", force_refresh=True)

        mock_client_cls.assert_called_with(timeout=35.0)
        assert res["count"] == 4
        assert "META" in res["batch_data"]


