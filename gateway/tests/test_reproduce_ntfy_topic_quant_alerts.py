"""
gateway/tests/test_reproduce_ntfy_topic_quant_alerts.py
Reproduction test for defect: SPX Level alerts missing notification because topic was hardcoded to 'spx_alerts' instead of canonical 'quant_alerts'.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from app.engine.level_alert_monitor import LevelAlertMonitor


def test_reproduce_ntfy_topic_broadcasts_to_quant_alerts():
    """
    RED GATE TEST:
    The user's mobile NTFY client is subscribed to 'quant_alerts' (the standard Quant fleet topic).
    dispatch_ntfy_alert must send to 'quant_alerts' (and support multi-topic broadcast).
    If it only sends to 'spx_alerts', users subscribed to 'quant_alerts' miss notifications.
    """
    monitor = LevelAlertMonitor()
    alert = {
        "id": "alt-test-7515",
        "ticker": "SPX",
        "level_price": 7515.0,
        "level_type": "BUY",
        "level_price_range": "7515.00 - 7522.00",
        "touched_boundary": 7522.0,
        "current_spot": 7523.09,
        "distance_pts": 1.09,
        "comments": "IMM SUP test",
        "timestamp": "2026-09-16T15:16:16-04:00"
    }

    with patch("common_lib.connectors.nfty.send_ntfy_notification") as mock_send:
        monitor.dispatch_ntfy_alert(alert)

        assert mock_send.called, "send_ntfy_notification must be called"
        
        # Collect all topics that received notifications
        dispatched_topics = [call_args.kwargs.get("topic") for call_args in mock_send.call_args_list]
        
        # Hard assertion: 'quant_alerts' MUST be in dispatched_topics
        assert "quant_alerts" in dispatched_topics, (
            f"'quant_alerts' must receive the notification so mobile NTFY subscribers receive it! "
            f"Currently dispatched only to: {dispatched_topics}"
        )
