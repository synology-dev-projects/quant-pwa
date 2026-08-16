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
