import asyncio
import pytest
from unittest.mock import patch, MagicMock
from app.engine.level_alert_monitor import LevelAlertMonitor


def test_reproduce_spx_range_level_alert_labeling():
    """
    REPRODUCTION TEST: SPX Range Level Alert Labeling and Boundary Detection
    Bug: When SPX enters a range level (e.g. BUY 7565 - 7575) at the upper edge (spot = 7575.00),
    the current implementation labels the alert solely as 'BUY @ 7565.00' with level_price = 7565.0,
    completely omitting the 7575.00 boundary that was actually entered.
    Expected: 
      1. The alert should record 'level_price_range': '7565.00 - 7575.00'.
      2. The alert should record 'touched_boundary': 7575.00.
      3. The NTFY dispatch title must explicitly state the range and touched price:
         'SPX Level Hit: BUY @ 7565.00 - 7575.00 (Touched 7575.00)'.
    """
    monitor = LevelAlertMonitor()
    
    levels = [{
        "start_lvl_price": 7565.00,
        "end_lvl_price": 7575.00,
        "buy_sell_ind": "BUY",
        "comments": "Immediate Support Range",
        "session_date": "2026-09-15"
    }]

    spot = 7575.00
    alerts = asyncio.run(monitor.check_proximity(spot, levels))
    
    assert len(alerts) == 1, "Expected 1 alert when spot enters range at 7575.00"
    alert = alerts[0]
    
    assert "level_price_range" in alert, "Alert must contain 'level_price_range' for range levels"
    assert alert["level_price_range"] == "7565.00 - 7575.00"
    
    assert "touched_boundary" in alert, "Alert must identify the touched boundary"
    assert alert["touched_boundary"] == 7575.00

    with patch("common_lib.connectors.nfty.send_ntfy_notification") as mock_ntfy:
        monitor.dispatch_ntfy_alert(alert)
        assert mock_ntfy.called
        call_kwargs = mock_ntfy.call_args[1]
        title = call_kwargs["title"]
        assert "7565.00 - 7575.00" in title, f"NTFY title should contain full range, got: {title}"
        assert "7575.00" in title, f"NTFY title should contain touched price 7575.00, got: {title}"
