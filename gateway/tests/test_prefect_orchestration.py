"""
Unit and Integration Tests for Prefect Pipeline Orchestrator.
Verifies that only Flow and Quant Levels are active, that inactive pipelines
are cleanly gated, and that the runner delegates execution correctly.
"""

import unittest
from unittest.mock import patch, MagicMock

try:
    from prefect.testing.utilities import prefect_test_harness
except ImportError:
    from contextlib import nullcontext as prefect_test_harness


class TestPrefectOrchestration(unittest.TestCase):

    def test_prefect_flow_registration(self):
        """Verify that the Prefect flow is registered and contains the active tasks."""
        from common_lib.orchestration.prefect_flow import daily_market_cycle_flow, ACTIVE_PIPELINES, INACTIVE_PIPELINES

        self.assertIn("quant_levels", ACTIVE_PIPELINES)
        self.assertIn("unusual_options_flow", ACTIVE_PIPELINES)
        self.assertNotIn("gexdex_snapshot", ACTIVE_PIPELINES)
        self.assertNotIn("market_confluence", ACTIVE_PIPELINES)
        self.assertIn("gexdex_snapshot", INACTIVE_PIPELINES)
        self.assertIn("market_confluence", INACTIVE_PIPELINES)

        # Check flow metadata
        self.assertEqual(daily_market_cycle_flow.name, "daily-market-cycle")

    def test_prefect_flow_execution_active_only(self):
        """Verify that executing the flow only executes active pipelines."""
        from common_lib.orchestration.prefect_flow import daily_market_cycle_flow

        with prefect_test_harness():
            with patch("common_lib.orchestration.prefect_flow.execute_quant_levels") as mock_levels, \
                 patch("common_lib.orchestration.prefect_flow.execute_unusual_flow") as mock_flow, \
                 patch("common_lib.orchestration.prefect_flow.execute_snapshot") as mock_snap, \
                 patch("common_lib.orchestration.prefect_flow.execute_confluence") as mock_conf:

                mock_levels.return_value = {"status": "SUCCESS", "rows": 100}
                mock_flow.return_value = {"status": "SUCCESS", "rows": 200}

                res = daily_market_cycle_flow(session_date="2026-10-02")
                self.assertEqual(res["quant_levels"]["status"], "SUCCESS")
                self.assertEqual(res["unusual_options_flow"]["status"], "SUCCESS")

                mock_levels.assert_called_once()
                mock_flow.assert_called_once()
                mock_snap.assert_not_called()
                mock_conf.assert_not_called()

    def test_prefect_flow_execution_selective_inactive_rejected(self):
        """Verify that requesting an inactive pipeline explicitly returns an INACTIVE state."""
        from common_lib.orchestration.prefect_flow import daily_market_cycle_flow

        with prefect_test_harness():
            res = daily_market_cycle_flow(only_pipeline="gexdex_snapshot")
            self.assertIn("gexdex_snapshot", res)
            self.assertEqual(res["gexdex_snapshot"]["status"], "INACTIVE")


if __name__ == "__main__":
    unittest.main()
