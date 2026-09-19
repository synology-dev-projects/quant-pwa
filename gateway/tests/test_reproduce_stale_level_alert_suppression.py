import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from app.engine.level_alert_monitor import LevelAlertMonitor

NY_TZ = ZoneInfo("America/New_York")


def test_reproduce_stale_level_alerts_suppression():
    """
    REPRODUCTION TEST: Stale / Expired Session Levels Must Not Fire Alerts on Today's Spot Price
    
    Bug: On Friday 2026-09-18, the user received an alert:
      'SPX Level Hit: SELL @ 7652.00 - 7662.00 (Touched 7652.00)'
      when today's SPX touched 7651.04.
      However, 7652.00 - 7662.00 was an expired SELL level from Monday 2026-09-14!
      Today's actual SELL level was 7687 - 7700.
      
    Root Cause:
      1. fetch_active_spx_levels() did an unconstrained MAX(datetime::date) without validating
         that the date matches the expected active trading session.
      2. check_proximity() blindly evaluated levels without checking if the level's session_date
         is stale compared to the active trading date.
         
    Expected:
      1. When DB only has levels from 2026-09-14 and expected session date is 2026-09-18,
         fetch_active_spx_levels() must return [] (empty list) rather than obsolete levels.
      2. If stale levels (e.g. session_date='2026-09-14') are evaluated against a spot price
         on 2026-09-18, check_proximity() must suppress them and return 0 alerts.
    """
    monitor = LevelAlertMonitor()

    # 1. Test check_proximity suppression for stale levels
    # Simulated current trading day is 2026-09-18 (Friday)
    stale_level = {
        "start_lvl_price": 7652.00,
        "end_lvl_price": 7662.00,
        "buy_sell_ind": "SELL",
        "comments": "Expired Monday resistance",
        "session_date": "2026-09-14"  # 4 days old!
    }

    spot_today = 7651.04  # Touches 7652.00 (|7651.04 - 7652.00| = 0.96 <= 1.50)

    with patch.object(monitor, "dispatch_ntfy_alert") as mock_dispatch:
        alerts = asyncio.run(monitor.check_proximity(spot_today, [stale_level]))

    # If the bug exists, alerts will have length 1 (triggering false alert on 2026-09-14 level)
    assert len(alerts) == 0, (
        f"DEFECT REPRODUCED: check_proximity() triggered {len(alerts)} alert(s) for a stale level "
        f"from session {stale_level['session_date']} against today's spot price {spot_today}!"
    )
