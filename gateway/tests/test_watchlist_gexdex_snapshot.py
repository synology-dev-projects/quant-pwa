import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token
from app.routers.radar import RadarUnifiedRow, RadarUnifiedResponse

client = TestClient(app)


# ==============================================================================
# 1. CONFLUENCE RADAR API & FILTERING TESTS
# ==============================================================================

def test_radar_unified_row_watchlist_tag_model():
    row = RadarUnifiedRow(
        ticker='TSLA',
        snapshot_date='2026-09-14',
        spot_price=220.0,
        formatted_spot_price='$220.00',
        source_scorecards=['WATCHLIST'],
        is_watchlist=True
    )
    assert row.is_watchlist is True
    assert 'WATCHLIST' in row.source_scorecards


def test_radar_unified_table_source_filtering():
    token, _ = create_session_token()
    headers = {'Authorization': f'Bearer {token}'}

    # Test filtering by source=WATCHLIST
    res_wl = client.get('/api/radar/unified-table?source=WATCHLIST', headers=headers)
    assert res_wl.status_code == 200
    data_wl = res_wl.json()
    assert 'rows' in data_wl
    assert 'watchlist_count' in data_wl
    assert 'flow_leaders_count' in data_wl
    for r in data_wl['rows']:
        assert r['is_watchlist'] is True or 'WATCHLIST' in r.get('source_scorecards', [])

    # Test filtering by source=FLOW
    res_flow = client.get('/api/radar/unified-table?source=FLOW', headers=headers)
    assert res_flow.status_code == 200
    data_flow = res_flow.json()
    for r in data_flow['rows']:
        assert any(x != 'WATCHLIST' for x in r.get('source_scorecards', []))


# ==============================================================================
# 2. SNAPSHOT SYNC TRIGGER ENDPOINT TEST
# ==============================================================================

def test_snapshot_sync_trigger_endpoint():
    token, _ = create_session_token()
    headers = {'Authorization': f'Bearer {token}'}

    with patch('app.routers.snapshot_status.resolve_runner') as mock_resolve:
        mock_resolve.return_value = MagicMock(return_value=(25, date(2026, 9, 14), 'Committed 25 snapshot rows'))
        res = client.post('/api/snapshot/sync', headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body['status'] == 'ok'
        assert body['rows_upserted'] == 25
        assert body['snapshot_date'] == '2026-09-14'
