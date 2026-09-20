import pytest
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from unittest.mock import patch

from app.routers.snapshot_status import get_market_calendar_context
from app.routers.flow_status import get_last_market_day

NY_TZ = ZoneInfo("America/New_York")


def test_reproduce_market_open_session_date_alignment():
    """
    REPRODUCTION TEST: Market-Open Pipeline Session Date Parity
    The pipeline is designed to run at Market Open (09:15-09:30 AM ET)
    based on the last completed session data.
    """
    # Case 1: Market Open morning run at 09:15 AM ET on Thursday Sep 10, 2026
    thursday_morning = datetime(2026, 9, 10, 9, 15, tzinfo=NY_TZ)
    _, _, expected_session = get_market_calendar_context(thursday_morning)
    expected_flow_day = get_last_market_day(thursday_morning)
    
    # At market open on Thursday Sep 10, both must target Wednesday Sep 9
    assert expected_session == date(2026, 9, 9)
    assert expected_session == expected_flow_day

    # Case 2: Post-market evening at 17:00 ET on Thursday Sep 10, 2026
    thursday_evening = datetime(2026, 9, 10, 17, 0, tzinfo=NY_TZ)
    _, _, expected_evening_session = get_market_calendar_context(thursday_evening)
    flow_day_evening = get_last_market_day(thursday_evening)
    assert expected_evening_session == flow_day_evening
