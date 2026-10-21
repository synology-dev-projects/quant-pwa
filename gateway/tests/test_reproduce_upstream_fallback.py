"""
REPRODUCTION TEST: Pipeline Upstream Dependency Data Freshness Fallback
Reproduction for issue where downstream pipelines (e.g. market_confluence) are
BLOCKED when upstreams ran standalone and populated target tables but did not
register a row in pipeline_runs.
"""

import pytest
from datetime import date
import sqlalchemy as sa
from common_lib.orchestration.state import ensure_pipeline_runs_table, check_upstream_dependencies
from common_lib.orchestration.registry import get_registered_dag


def test_reproduce_upstream_fallback_when_target_table_populated():
    """
    Expected: If pipeline_runs has no entry for an upstream dependency, but the upstream's
              target table has populated records for session_date, check_upstream_dependencies()
              should fall back to verifying target table data, returning is_ready=True and blocked_by=[].
    Actual (Prior to patch): check_upstream_dependencies() only queries pipeline_runs, sees no row,
                             and marks is_ready=False with blocked_by=['unusual_option_flow', 'gexdex_snapshot'].
    """
    # 1. Arrange: In-memory SQLite engine
    engine = sa.create_engine("sqlite:///:memory:")
    ensure_pipeline_runs_table(engine)

    session_dt = date(2026, 10, 20)

    # Populate upstream target tables with records for session_date
    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE unusual_option_flow_te (
                flow_id TEXT PRIMARY KEY,
                trade_date TEXT,
                symbol TEXT,
                premium REAL
            )
        """))
        conn.execute(sa.text("""
            INSERT INTO unusual_option_flow_te (flow_id, trade_date, symbol, premium)
            VALUES ('flow-1', '2026-10-20', 'META', 23000000.0)
        """))

        conn.execute(sa.text("""
            CREATE TABLE gexdex_snapshot (
                snapshot_date TEXT,
                ticker TEXT,
                spot_price REAL
            )
        """))
        conn.execute(sa.text("""
            INSERT INTO gexdex_snapshot (snapshot_date, ticker, spot_price)
            VALUES ('2026-10-20', 'META', 697.52)
        """))

    # Notice: pipeline_runs table is EMPTY for session_dt!
    # 2. Act: Check upstream dependencies for market_confluence
    is_ready, blocked_by, upstream_statuses = check_upstream_dependencies(
        engine, "market_confluence", session_dt
    )

    # 3. Assert: Must be ready via target table data freshness fallback
    assert is_ready is True, f"Expected is_ready=True via table data fallback, got False (blocked by: {blocked_by})"
    assert len(blocked_by) == 0, f"Expected 0 blocked dependencies, got {blocked_by}"
