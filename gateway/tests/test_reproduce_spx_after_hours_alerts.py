import pytest
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

from app.engine.level_alert_monitor import LevelAlertMonitor

NY_TZ = ZoneInfo("America/New_York")


def test_reproduce_spx_alert_triggers_after_hours_bug():
    """
    REPRODUCTION TEST:
    Prior to the fix, check_proximity(...) does not verify market hours.
    When SPX spot price touches an active level after regular market hours
    (e.g., Wednesday at 18:30 ET, or weekend Saturday 12:00 ET),
    it generates alerts and dispatches push notifications.

    With market hours enforcement:
    Outside 09:30 - 16:15 ET (Mon-Fri), alerts MUST NOT be evaluated or dispatched!
    """
    monitor = LevelAlertMonitor()
    levels = [{
        "start_lvl_price": 6020.00,
        "end_lvl_price": None,
        "buy_sell_ind": "BUY",
        "comments": "After hours test shelf",
        "session_date": "2026-09-24",
    }]

    # Wednesday evening at 18:30 ET (After hours)
    after_hours_dt = datetime(2026, 9, 23, 18, 30, tzinfo=NY_TZ)

    with patch("app.engine.level_alert_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = after_hours_dt
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        with patch.object(monitor, "dispatch_ntfy_alert") as mock_dispatch:
            mock_dispatch.return_value = True

            # We pass spot price 6020.00 directly hitting the level
            alerts = asyncio.run(monitor.check_proximity(spot=6020.00, levels=levels, enforce_market_hours=True))

            # BUG BEHAVIOR (PRE-FIX):
            # len(alerts) == 1, alert dispatched after hours!
            # DESIRED BEHAVIOR (FIXED):
            # len(alerts) == 0, mock_dispatch.assert_not_called()
            assert len(alerts) == 0, f"Expected 0 alerts after hours, but got: {len(alerts)}"
            mock_dispatch.assert_not_called()


def test_reproduce_spx_alert_triggers_on_weekend_bug():
    """
    REPRODUCTION TEST:
    On Saturday/Sunday, SPX proximity alerts must be suppressed.
    """
    monitor = LevelAlertMonitor()
    levels = [{
        "start_lvl_price": 6020.00,
        "end_lvl_price": None,
        "buy_sell_ind": "BUY",
        "comments": "Weekend test shelf",
        "session_date": "2026-09-26",
    }]

    # Saturday at 14:00 ET
    weekend_dt = datetime(2026, 9, 26, 14, 0, tzinfo=NY_TZ)

    with patch("app.engine.level_alert_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = weekend_dt
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        with patch.object(monitor, "dispatch_ntfy_alert") as mock_dispatch:
            mock_dispatch.return_value = True

            alerts = asyncio.run(monitor.check_proximity(spot=6020.00, levels=levels, enforce_market_hours=True))
            assert len(alerts) == 0, f"Expected 0 alerts on weekend, but got: {len(alerts)}"
            mock_dispatch.assert_not_called()


def test_spx_alert_triggers_during_market_hours():
    """
    SYMMETRIC VERIFICATION:
    During regular market hours (e.g. Wednesday 10:30 ET),
    proximity detection and dispatch MUST function as expected.
    """
    monitor = LevelAlertMonitor()
    levels = [{
        "start_lvl_price": 6020.00,
        "end_lvl_price": None,
        "buy_sell_ind": "BUY",
        "comments": "In-market test shelf",
        "session_date": "2026-09-23",
    }]

    market_dt = datetime(2026, 9, 23, 10, 30, tzinfo=NY_TZ)

    with patch.object(monitor, "dispatch_ntfy_alert") as mock_dispatch:
        mock_dispatch.return_value = True

        alerts = asyncio.run(monitor.check_proximity(spot=6020.50, levels=levels, now=market_dt))
        assert len(alerts) == 1
        assert alerts[0]["level_price"] == 6020.00
        mock_dispatch.assert_called_once()

