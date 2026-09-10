import pytest
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from unittest.mock import patch

from app.engine.snapshot_pipeline import get_expected_trade_session
from app.routers.flow_status import get_last_market_day

NY_TZ = ZoneInfo("America/New_York")


def test_reproduce_market_open_session_date_alignment():
    """
    REPRODUCTION TEST: Market-Open Pipeline Session Date Parity
    The pipeline is designed to run at Market Open (09:15-09:30 AM ET)
    based on the last completed session data.
    
    Bug: snapshot_pipeline.get_expected_trade_session() previously had a 16:30 ET
    post-close cutoff that switched to 'today', causing a disparity with flow_status
    and attempting to process today's unfinalized session in the evening instead
    of delegating to get_last_market_day().
    """
    # Case 1: Market Open morning run at 09:15 AM ET on Thursday Sep 10, 2026
    thursday_morning = datetime(2026, 9, 10, 9, 15, tzinfo=NY_TZ)
    
    with patch("app.engine.snapshot_pipeline.datetime") as mock_dt:
        mock_dt.now.return_value = thursday_morning
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        
        expected_session = get_expected_trade_session()
        expected_flow_day = get_last_market_day(thursday_morning)
        
        # At market open on Thursday Sep 10, both must target Wednesday Sep 9
        assert expected_session == date(2026, 9, 9)
        assert expected_session == expected_flow_day

    # Case 2: Post-market evening at 17:00 ET on Thursday Sep 10, 2026
    # For a market-open pipeline running on last session data, it must remain aligned
    # with get_last_market_day() rather than prematurely requiring today's flow.
    thursday_evening = datetime(2026, 9, 10, 17, 0, tzinfo=NY_TZ)
    with patch("app.engine.snapshot_pipeline.datetime") as mock_dt:
        mock_dt.now.return_value = thursday_evening
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        
        expected_evening_session = get_expected_trade_session()
        flow_day_evening = get_last_market_day(thursday_evening)
        
        # FAILS BEFORE FIX: get_expected_trade_session() returns 2026-09-10 (today)
        # while get_last_market_day() returns 2026-09-09
        assert expected_evening_session == flow_day_evening, (
            f"Expected parity with get_last_market_day ({flow_day_evening}), "
            f"but got {expected_evening_session}"
        )
