"""
gateway/tests/test_reproduce_pipeline_failure_alerts.py - Reproduction test for missing pipeline failure alerts.

Verifies that when any pipeline (GEX/DEX snapshot, unusual options flow, quant levels, market confluence)
encounters an unexpected failure or fatal exception, a Priority 5 failure alert is dispatched to NTFY
topic 'quant_alerts'.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date


def test_snapshot_pipeline_failure_dispatches_alert():
    """Verifies that trigger_snapshot_sync dispatches failure alert on crash."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.auth import create_session_token

    client = TestClient(app)
    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.routers.snapshot_status.resolve_runner", side_effect=RuntimeError("TradingEdge 429 Too Many Requests")), \
         patch("common_lib.connectors.alerts.dispatch_pipeline_failure_alert") as mock_alert:

        res = client.post("/api/snapshot/sync", headers=headers)
        assert res.status_code == 500
        assert mock_alert.called
        assert "GEX/DEX Snapshot" in mock_alert.call_args[0][0]


def test_flow_runner_failure_dispatches_alert():
    """Verifies that common_lib.flow.runner dispatches Priority 5 failure alert on crash."""
    from common_lib.flow import runner as flow_runner

    with patch("common_lib.flow.runner.load.get_latest_recorded_date", return_value=date(2026, 9, 18)), \
         patch("common_lib.flow.runner.extract.get_authenticated_flow_session", side_effect=RuntimeError("Session cookie expired")), \
         patch("common_lib.connectors.nfty.send_ntfy_notification") as mock_ntfy:

        try:
            flow_runner.run_daily_incremental()
        except Exception:
            pass

        assert mock_ntfy.called, "Expected send_ntfy_notification to be called on flow runner failure"
        call_kwargs = mock_ntfy.call_args.kwargs if mock_ntfy.call_args.kwargs else {}
        call_args = mock_ntfy.call_args.args if mock_ntfy.call_args.args else ()

        topic = call_kwargs.get("topic") or (call_args[1] if len(call_args) > 1 else None)
        priority = call_kwargs.get("priority") or (call_args[4] if len(call_args) > 4 else None)

        assert topic == "quant_alerts", f"Expected topic 'quant_alerts', got {topic}"
        assert priority == 5, f"Expected Priority 5, got {priority}"


def test_quant_levels_runner_failure_dispatches_alert():
    """Verifies that common_lib.quant_levels.runner dispatches Priority 5 failure alert on crash."""
    from common_lib.quant_levels import runner as levels_runner

    with patch("common_lib.quant_levels.runner.load._get_latest_recorded_date", return_value=date(2026, 9, 18)), \
         patch("common_lib.quant_levels.runner.extract.run", side_effect=RuntimeError("Mighty feed connection timeout")), \
         patch("common_lib.connectors.nfty.send_ntfy_notification") as mock_ntfy:

        try:
            levels_runner.run_daily_incremental()
        except Exception:
            pass

        assert mock_ntfy.called, "Expected send_ntfy_notification to be called on quant levels runner failure"
        call_kwargs = mock_ntfy.call_args.kwargs if mock_ntfy.call_args.kwargs else {}
        call_args = mock_ntfy.call_args.args if mock_ntfy.call_args.args else ()

        topic = call_kwargs.get("topic") or (call_args[1] if len(call_args) > 1 else None)
        priority = call_kwargs.get("priority") or (call_args[4] if len(call_args) > 4 else None)

        assert topic == "quant_alerts", f"Expected topic 'quant_alerts', got {topic}"
        assert priority == 5, f"Expected Priority 5, got {priority}"


def test_centralized_alert_dispatcher_zero_config_fallback():
    """Verifies that dispatch_pipeline_failure_alert works even with no config or broken config."""
    from common_lib.connectors.alerts import dispatch_pipeline_failure_alert, resolve_ntfy_endpoint

    # 1. Fallback endpoint resolves to canonical https://richntfynotifier.synology.me
    with patch.dict("os.environ", {}, clear=True):
        endpoint = resolve_ntfy_endpoint(None)
        assert endpoint == "https://richntfynotifier.synology.me"

    # 2. Endpoint with /alerts suffix is properly stripped
    mock_config = MagicMock()
    mock_config.ntfy_endpoint = "https://richntfynotifier.synology.me/alerts"
    assert resolve_ntfy_endpoint(mock_config) == "https://richntfynotifier.synology.me"

    # 3. Dispatches successfully
    with patch("common_lib.connectors.nfty.send_ntfy_notification") as mock_send:
        res = dispatch_pipeline_failure_alert(
            pipeline_name="Test Pipeline",
            error=RuntimeError("Simulated critical error"),
            session_date="2026-09-18"
        )
        assert res is True
        assert mock_send.called
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["topic"] == "quant_alerts"
        assert call_kwargs["priority"] == 5
        assert "Simulated critical error" in call_kwargs["message"]
        assert "Test Pipeline" in call_kwargs["title"]
