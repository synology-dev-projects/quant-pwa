import pytest
from datetime import date
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token

client = TestClient(app)


def test_reproduce_radar_latest_session_is_last_market_day():
    """
    Reproduction test for issue:
    'the latest session date should always be the last market day. currently it's the current market day'

    When daily_confluence_summary contains a record for a non-market day (e.g. Labor Day 2026-09-07)
    or a current in-session day with 0 scanned plays, /api/scanner/latest and /api/scanner/dates
    must NOT return that empty/current date as the latest session.
    They must return the last market day with valid confluence data (2026-09-04).
    """
    token, _ = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Probe /api/scanner/latest
    res_latest = client.get("/api/scanner/latest", headers=headers)
    assert res_latest.status_code == 200, f"Expected 200, got {res_latest.status_code}: {res_latest.text}"
    latest_data = res_latest.json()

    # The latest session date MUST be the last market day with valid data ('2026-09-04'), NOT the current market/calendar day ('2026-09-07')
    scan_date = latest_data.get("scan_date")
    assert scan_date != "2026-09-07", (
        f"DEFECT REPRODUCED: /api/scanner/latest returned current calendar/non-market day '{scan_date}' "
        f"instead of the last completed market day ('2026-09-04')."
    )
    assert scan_date == "2026-09-04", f"Expected last market day '2026-09-04', got '{scan_date}'"

    summary = latest_data.get("summary") or {}
    assert summary.get("total_scanned_count", 0) > 0, "Latest session must have valid qualifying scans"

    # 2. Probe /api/scanner/dates
    res_dates = client.get("/api/scanner/dates", headers=headers)
    assert res_dates.status_code == 200
    dates = res_dates.json()
    assert "2026-09-07" not in dates, (
        f"DEFECT REPRODUCED: /api/scanner/dates included non-market/empty date '2026-09-07' in available sessions: {dates}"
    )
    assert dates and dates[0] == "2026-09-04", (
        f"First option in available session dates must be last market day '2026-09-04', got {dates}"
    )
