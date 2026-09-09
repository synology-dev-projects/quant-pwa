import pytest
from datetime import datetime, date
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.routers.snapshot_status import get_market_calendar_context, get_snapshot_status
from app.routers.flow_status import get_flow_status, get_last_market_day

client = TestClient(app)


def test_reproduce_snapshot_flow_parity_tuesday_late_night():
    """
    REPRODUCTION & REGRESSION TEST (DEFECT-gexdex-snapshot-sync-parity):
    When user checks status late Tuesday night (e.g. 2026-09-08 21:56 PT / 2026-09-09 00:56 ET):
    - Both flow and snapshot databases have session 2026-09-04 (Friday before Labor Day).
    - Flow evaluates as 'synced' with is_fresh=True because last_market_day is 2026-09-04.
    - Snapshot MUST also evaluate as 'synced' with is_fresh=True, matching Flow 100%.
    - Under the bug, snapshot rolled over into Wednesday 2026-09-09 prematurely, expecting 2026-09-09
      and returning status='stale' while Flow was 'synced'.
    """
    ref_dt = datetime(2026, 9, 8, 21, 56)

    # 1. Verify calendar helper parity
    expected_mkt_day = get_last_market_day(ref_dt)
    assert expected_mkt_day == date(2026, 9, 4), f"Expected 2026-09-04, got {expected_mkt_day}"

    is_mkt, today_d, snap_last_mkt = get_market_calendar_context(ref_dt)
    assert snap_last_mkt == expected_mkt_day, (
        f"Snapshot last_market_day ({snap_last_mkt}) must match flow get_last_market_day ({expected_mkt_day})"
    )

    # 2. Mock DB responses with actual DB state (latest date 2026-09-04)
    tbl_df = pd.DataFrame([{"tbl_exists": True}])
    snapshot_summary_df = pd.DataFrame([{
        "max_date": "2026-09-04",
        "total_count": 16,
        "latest_day_count": 16
    }])
    flow_summary_df = pd.DataFrame([{
        "max_date": "2026-09-04",
        "total_count": 2855,
        "expected_day_count": 107
    }])

    with patch("app.routers.flow_status.datetime") as mock_flow_dt, \
         patch("app.routers.snapshot_status.datetime") as mock_snap_dt, \
         patch("common_lib.connectors.postgres.sql") as mock_sql:

        mock_flow_dt.now.return_value = ref_dt
        mock_snap_dt.now.return_value = ref_dt

        def fake_sql(config, sql_text, params=None):
            if "information_schema.tables" in sql_text:
                return tbl_df
            elif "gexdex_snapshot" in sql_text:
                return snapshot_summary_df
            elif "unusual_option_flow_te" in sql_text:
                return flow_summary_df
            return pd.DataFrame()

        mock_sql.side_effect = fake_sql

        flow_res = client.get("/api/flow/status")
        snap_res = client.get("/api/snapshot/status")

        assert flow_res.status_code == 200
        assert snap_res.status_code == 200

        flow_data = flow_res.json()
        snap_data = snap_res.json()

        # Strict Parity Assertions
        assert flow_data["status"] == "synced", f"Flow should be synced, got {flow_data['status']}"
        assert snap_data["status"] == "synced", (
            f"Snapshot status ({snap_data['status']}) MUST match flow status ({flow_data['status']})"
        )
        assert snap_data["is_fresh"] is True
        assert snap_data["latest_snapshot_date"] == "2026-09-04"
        assert snap_data["expected_date"] == "2026-09-04"
