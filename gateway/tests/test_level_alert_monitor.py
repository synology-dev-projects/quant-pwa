import pytest
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.engine.level_alert_monitor import LevelAlertMonitor, level_alert_monitor
from app.core.auth import create_session_token

client = TestClient(app)
NY_TZ = ZoneInfo("America/New_York")


import asyncio

# ==============================================================================
# PROXIMITY DETECTION & COOLDOWN UNIT TESTS
# ==============================================================================

def test_hit_detection_within_threshold():
    """Spot 6020.85 vs Level 6020.00 (|0.85| <= 1.50) triggers alert."""
    monitor = LevelAlertMonitor()
    levels = [{
        "start_lvl_price": 6020.00,
        "end_lvl_price": None,
        "buy_sell_ind": "BUY",
        "comments": "Daily bounce shelf",
        "session_date": monitor.get_expected_session_date().strftime("%Y-%m-%d")
    }]

    with patch.object(monitor, "dispatch_ntfy_alert") as mock_dispatch:
        mock_dispatch.return_value = True
        alerts = asyncio.run(monitor.check_proximity(spot=6020.85, levels=levels))

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["ticker"] == "SPX"
    assert alert["level_price"] == 6020.00
    assert alert["level_type"] == "BUY"
    assert alert["current_spot"] == 6020.85
    assert alert["distance_pts"] == 0.85
    assert alert["comments"] == "Daily bounce shelf"
    assert len(monitor.recent_alerts) == 1
    assert 6020.00 in monitor.cooldown_map


def test_miss_detection_outside_threshold():
    """Spot 6025.00 vs Level 6020.00 (|5.00| > 1.50) does not trigger."""
    monitor = LevelAlertMonitor()
    levels = [{
        "start_lvl_price": 6020.00,
        "end_lvl_price": None,
        "buy_sell_ind": "BUY",
        "comments": "Support level",
    }]

    with patch.object(monitor, "dispatch_ntfy_alert") as mock_dispatch:
        alerts = asyncio.run(monitor.check_proximity(spot=6025.00, levels=levels))

    assert len(alerts) == 0
    assert len(monitor.recent_alerts) == 0
    assert 6020.00 not in monitor.cooldown_map
    mock_dispatch.assert_not_called()


def test_range_level_proximity_detection():
    """Range level 6010 to 6020: spot 6021.20 is within 1.5 pts of upper bound."""
    monitor = LevelAlertMonitor()
    levels = [{
        "start_lvl_price": 6010.00,
        "end_lvl_price": 6020.00,
        "buy_sell_ind": "SELL",
        "comments": "Supply band",
    }]

    with patch.object(monitor, "dispatch_ntfy_alert") as mock_dispatch:
        alerts = asyncio.run(monitor.check_proximity(spot=6021.20, levels=levels))

    assert len(alerts) == 1
    assert alerts[0]["level_price"] == 6010.00
    assert alerts[0]["level_type"] == "SELL"
    assert alerts[0]["distance_pts"] == 1.20


def test_15_minute_cooldown_suppression():
    """Second hit within 15 minutes is suppressed; hit after 15 minutes triggers."""
    monitor = LevelAlertMonitor()
    levels = [{
        "start_lvl_price": 6020.00,
        "buy_sell_ind": "BUY",
        "comments": "Key level",
    }]

    start_time = 1000000.0

    with patch("time.time", return_value=start_time):
        with patch.object(monitor, "dispatch_ntfy_alert"):
            alerts1 = asyncio.run(monitor.check_proximity(spot=6020.50, levels=levels))
    assert len(alerts1) == 1

    # Second hit at minute 5 (300s later) -> should be suppressed
    with patch("time.time", return_value=start_time + 300.0):
        with patch.object(monitor, "dispatch_ntfy_alert") as mock_dispatch:
            alerts2 = asyncio.run(monitor.check_proximity(spot=6020.80, levels=levels))
    assert len(alerts2) == 0
    mock_dispatch.assert_not_called()

    # Third hit at minute 16 (960s later) -> should trigger!
    with patch("time.time", return_value=start_time + 960.0):
        with patch.object(monitor, "dispatch_ntfy_alert") as mock_dispatch:
            alerts3 = asyncio.run(monitor.check_proximity(spot=6020.20, levels=levels))
    assert len(alerts3) == 1
    mock_dispatch.assert_called_once()


def test_multi_level_independence():
    """Hits on 6020.00 and 6035.00 both fire without blocking each other."""
    monitor = LevelAlertMonitor()
    levels = [
        {"start_lvl_price": 6020.00, "buy_sell_ind": "BUY", "comments": "Level 1"},
        {"start_lvl_price": 6035.00, "buy_sell_ind": "SELL", "comments": "Level 2"}
    ]

    t0 = 1000000.0
    # First hit level 1
    with patch("time.time", return_value=t0):
        with patch.object(monitor, "dispatch_ntfy_alert"):
            alerts1 = asyncio.run(monitor.check_proximity(spot=6020.50, levels=levels))
    assert len(alerts1) == 1
    assert alerts1[0]["level_price"] == 6020.00

    # 2 minutes later, price moves to 6035.20 -> level 2 triggers independently
    with patch("time.time", return_value=t0 + 120.0):
        with patch.object(monitor, "dispatch_ntfy_alert") as mock_dispatch:
            alerts2 = asyncio.run(monitor.check_proximity(spot=6035.20, levels=levels))
    assert len(alerts2) == 1
    assert alerts2[0]["level_price"] == 6035.00
    mock_dispatch.assert_called_once()


# ==============================================================================
# NTFY DISPATCH TESTS
# ==============================================================================

def test_dispatch_ntfy_alert_contract():
    """Verifies send_ntfy_notification called with correct parameters."""
    monitor = LevelAlertMonitor()
    alert = {
        "id": "alt-test-1",
        "ticker": "SPX",
        "level_price": 6020.00,
        "level_type": "BUY",
        "current_spot": 6020.85,
        "distance_pts": 0.85,
        "comments": "Test level comments",
        "timestamp": "2026-09-15T10:00:00-04:00"
    }

    with patch("common_lib.connectors.nfty.send_ntfy_notification") as mock_send:
        success = monitor.dispatch_ntfy_alert(alert)

    assert success is True
    assert mock_send.call_count == 2
    dispatched_topics = [call_args[1]["topic"] for call_args in mock_send.call_args_list]
    assert "quant_alerts" in dispatched_topics
    assert "spx_alerts" in dispatched_topics
    for call_args in mock_send.call_args_list:
        kwargs = call_args[1]
        assert kwargs["endpoint"] == "https://richntfynotifier.synology.me"
        assert kwargs["priority"] == 5
        assert kwargs["tags"] == "chart_with_upwards_trend,bell"
        assert "SPX Level Hit: BUY @ 6020.00" in kwargs["title"]
        assert "6020.85" in kwargs["message"]


def test_dispatch_ntfy_alert_exception_handling():
    """Verifies exception in NTFY delivery does not crash."""
    monitor = LevelAlertMonitor()
    alert = {
        "level_price": 6020.00,
        "level_type": "BUY",
        "current_spot": 6020.85,
        "distance_pts": 0.85
    }

    with patch("common_lib.connectors.nfty.send_ntfy_notification", side_effect=Exception("Network error")):
        success = monitor.dispatch_ntfy_alert(alert)

    assert success is False


# ==============================================================================
# MARKET HOURS LOGIC TESTS
# ==============================================================================

def test_is_market_hours():
    monitor = LevelAlertMonitor()

    # Wednesday 10:00 ET -> Inside regular hours
    wed_market = datetime(2026, 9, 16, 10, 0, tzinfo=NY_TZ)
    assert monitor.is_market_hours(wed_market) is True

    # Wednesday 09:30 ET -> Open boundary
    wed_open = datetime(2026, 9, 16, 9, 30, tzinfo=NY_TZ)
    assert monitor.is_market_hours(wed_open) is True

    # Wednesday 16:15 ET -> Close boundary
    wed_close = datetime(2026, 9, 16, 16, 15, tzinfo=NY_TZ)
    assert monitor.is_market_hours(wed_close) is True

    # Wednesday 09:15 ET -> Pre-market
    wed_pre = datetime(2026, 9, 16, 9, 15, tzinfo=NY_TZ)
    assert monitor.is_market_hours(wed_pre) is False

    # Wednesday 16:30 ET -> After-hours
    wed_post = datetime(2026, 9, 16, 16, 30, tzinfo=NY_TZ)
    assert monitor.is_market_hours(wed_post) is False

    # Saturday 12:00 ET -> Weekend
    sat_noon = datetime(2026, 9, 19, 12, 0, tzinfo=NY_TZ)
    assert monitor.is_market_hours(sat_noon) is False


# ==============================================================================
# REST API ENDPOINT TESTS
# ==============================================================================

def test_get_alerts_status_endpoint():
    """GET /api/quant-levels/alerts/status returns valid diagnostics."""
    response = client.get("/api/quant-levels/alerts/status")
    assert response.status_code == 200
    data = response.json()
    assert "active" in data
    assert "is_market_hours" in data
    assert "market_session" in data
    assert "monitored_levels_count" in data
    assert "pending_cooldowns" in data


def test_get_alerts_recent_endpoint():
    """GET /api/quant-levels/alerts/recent returns array of alerts."""
    # Ensure test alert in deque
    level_alert_monitor.recent_alerts.append({
        "id": "alt-test-recent-1",
        "ticker": "SPX",
        "level_price": 6050.00,
        "level_type": "BUY",
        "current_spot": 6050.25,
        "distance_pts": 0.25,
        "comments": "Support check",
        "timestamp": "2026-09-15T11:00:00-04:00",
        "session_date": "2026-09-15"
    })

    response = client.get("/api/quant-levels/alerts/recent")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["count"] >= 1
    assert any(a["id"] == "alt-test-recent-1" for a in data["alerts"])


def test_post_alerts_test_endpoint_unauthorized():
    """POST /api/quant-levels/alerts/test without token returns 401."""
    response = client.post("/api/quant-levels/alerts/test", json={
        "test_spot": 6020.85,
        "test_level": 6020.00,
        "level_type": "BUY"
    })
    assert response.status_code == 401


def test_post_alerts_test_endpoint_authorized():
    """POST /api/quant-levels/alerts/test with token dispatches and returns 200."""
    token, _ = create_session_token(expires_in_hours=6)
    headers = {"Authorization": f"Bearer {token}"}

    with patch("common_lib.connectors.nfty.send_ntfy_notification") as mock_nfty:
        mock_nfty.return_value = MagicMock(status_code=200)
        response = client.post(
            "/api/quant-levels/alerts/test",
            headers=headers,
            json={
                "test_spot": 6020.85,
                "test_level": 6020.00,
                "level_type": "BUY"
            }
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "dispatched"
    assert "alert" in data
    assert data["alert"]["level_price"] == 6020.00
    assert data["alert"]["current_spot"] == 6020.85
    assert data["alert"]["distance_pts"] == 0.85
    assert data["alert"]["level_type"] == "BUY"
