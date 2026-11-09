"""
REPRODUCTION & SYMMETRIC VERIFICATION TEST:
Pipeline Scheduling, Date Alignment & Confluence Flow Fallback
Demonstrates:
1. market_confluence falls back to the latest available flow date when target_date has
   no flow, ensuring confluence runs every day.
2. pipelines_router accurately resolves today's session for quant_levels while resolving
   prior completed session for downstream flow, preventing false 'NOT_STARTED' in Settings.
"""

import sys
import os
from pathlib import Path
import pytest
from datetime import date, datetime, timedelta
import sqlalchemy as sa
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Ensure workspace repos on path
root_dir = Path(__file__).resolve().parent.parent.parent.parent
for p in [str(root_dir / "common-lib"), str(root_dir / "market-confluence-pipeline"), str(root_dir / "quant-pwa" / "gateway")]:
    if p not in sys.path:
        sys.path.insert(0, p)

from common_lib.orchestration.state import ensure_pipeline_runs_table, record_run_start, record_run_success
from src.pipeline.collector import collect_flow_candidates


def test_reproduce_confluence_missing_flow_fallback():
    """
    Verifies that when flow for the target trade date is missing (e.g. at market open or delayed upload),
    collect_flow_candidates falls back to the latest available flow date and extracts candidates.
    """
    engine = sa.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE unusual_option_flow_te (
                flow_id TEXT PRIMARY KEY,
                trade_date TEXT,
                symbol TEXT,
                order_type TEXT,
                strike_price REAL,
                strike_otm_pct REAL,
                expiration_date TEXT,
                open_interest INTEGER,
                is_unusual_oi INTEGER,
                premium REAL,
                net_score REAL
            )
        """))
        # Prior completed session flow (2026-11-05) exists
        conn.execute(sa.text("""
            INSERT INTO unusual_option_flow_te (
                flow_id, trade_date, symbol, order_type, strike_price,
                strike_otm_pct, expiration_date, open_interest, is_unusual_oi,
                premium, net_score
            ) VALUES (
                'flow-1', '2026-11-05', 'NVDA', 'Buy Call', 140.0,
                5.0, '2026-11-20', 1000, 1, 2500000.0, 1.5
            )
        """))

    # Target date is 2026-11-06 (Friday, which has 0 records)
    resolved_date, candidates = collect_flow_candidates(
        engine,
        target_date=date(2026, 11, 6),
        min_symbol_premium=1_000_000.0
    )

    # Must fall back to latest flow date (2026-11-05) and return candidates
    assert len(candidates) > 0, f"Expected candidates from fallback date 2026-11-05, got: {candidates}"
    assert resolved_date == date(2026, 11, 5), f"Expected resolved_date to fall back to 2026-11-05, got: {resolved_date}"


def test_reproduce_pipelines_router_date_mismatch_for_quant_levels():
    """
    Verifies that in pipelines_router.get_pipelines_status(), when no ?date= parameter is passed,
    quant_levels reports its SUCCESS status for today's session, rather than being stuck on 'NOT_STARTED'.
    """
    from app.main import app
    client = TestClient(app)

    engine = sa.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    ensure_pipeline_runs_table(engine)

    today = date(2026, 11, 9)
    last_market_day = date(2026, 11, 6)

    # Record quant_levels running for TODAY (Monday 2026-11-09)
    run_id = record_run_start(engine, "quant_levels", today)
    record_run_success(engine, run_id, rows_affected=15)

    with patch("app.routers.pipelines_router.load_config"), \
         patch("app.routers.pipelines_router.get_postgres_engine", return_value=engine), \
         patch("app.routers.pipelines_router.get_market_calendar_context", return_value=(True, today, last_market_day)):
        
        # Call GET /api/pipelines/status without date query parameter (default view in Settings modal)
        resp = client.get("/api/pipelines/status")
        assert resp.status_code == 200
        data = resp.json()
        
        pipe_status = data["pipelines"].get("quant_levels", {})
        assert pipe_status.get("status") == "SUCCESS", (
            f"Expected quant_levels to report SUCCESS, but got: {pipe_status.get('status')}"
        )
        assert pipe_status.get("session_date") == str(today)
        assert pipe_status.get("rows_affected") == 15
