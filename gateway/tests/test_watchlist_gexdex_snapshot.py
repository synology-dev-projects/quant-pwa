import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import create_session_token
from app.engine.snapshot_pipeline import (
    get_user_watchlist_tickers,
    generate_scorecard_watchlist,
)
from app.routers.radar import RadarUnifiedRow, RadarUnifiedResponse

client = TestClient(app)


# ==============================================================================
# 1. WATCHLIST TICKERS INGESTION & PIPELINE ENGINE TESTS
# ==============================================================================

def test_get_user_watchlist_tickers_success():
    mock_engine = MagicMock(spec=sa.Engine)
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    # Simulate rows with variations: lowercase, padded whitespace, duplicates
    mock_conn.execute.return_value.scalars.return_value.all.return_value = [
        'aapl', 'TSLA ', '  nvda', 'TSLA', 'pltr'
    ]

    tickers = get_user_watchlist_tickers(mock_engine)
    assert tickers == {'AAPL', 'TSLA', 'NVDA', 'PLTR'}


def test_get_user_watchlist_tickers_table_missing_fallback():
    mock_engine = MagicMock(spec=sa.Engine)
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.side_effect = Exception('relation quant_watchlist_tickers does not exist')

    tickers = get_user_watchlist_tickers(mock_engine)
    assert tickers == set()


def test_generate_scorecard_watchlist_includes_watchlist_tag():
    mock_engine = MagicMock(spec=sa.Engine)
    target_date = date(2026, 9, 14)

    with patch('app.engine.snapshot_pipeline.get_user_watchlist_tickers', return_value={'TSLA', 'PLTR'}),          patch('app.engine.snapshot_pipeline.get_available_trade_dates', return_value=[target_date]):
        
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.scalars.return_value.all.return_value = []

        result = generate_scorecard_watchlist(mock_engine, target_date)
        assert 'TSLA' in result
        assert 'PLTR' in result
        assert result['TSLA'] == ['WATCHLIST']
        assert result['PLTR'] == ['WATCHLIST']


def test_overlapping_tickers_preserve_both_tags():
    mock_engine = MagicMock(spec=sa.Engine)
    target_date = date(2026, 9, 14)

    with patch('app.engine.snapshot_pipeline.get_user_watchlist_tickers', return_value={'NVDA'}),          patch('app.engine.snapshot_pipeline.get_available_trade_dates', return_value=[target_date]):
        
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.scalars.return_value.all.return_value = ['NVDA']

        result = generate_scorecard_watchlist(mock_engine, target_date)
        assert 'NVDA' in result
        assert 'WATCHLIST' in result['NVDA']
        assert '3D_BULL_PREM' in result['NVDA']
        assert len(result['NVDA']) > 1


# ==============================================================================
# 2. CONFLUENCE RADAR API & FILTERING TESTS
# ==============================================================================

def test_radar_unified_row_watchlist_tag_model():
    row = RadarUnifiedRow(
        ticker='TSLA',
        snapshot_date='2026-09-14',
        spot_price=220.0,
        formatted_spot_price='.00',
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
# 3. SNAPSHOT SYNC TRIGGER ENDPOINT TEST
# ==============================================================================

def test_snapshot_sync_trigger_endpoint():
    token, _ = create_session_token()
    headers = {'Authorization': f'Bearer {token}'}

    with patch('app.engine.snapshot_pipeline.run_snapshot_pipeline', return_value=(25, date(2026, 9, 14), 'Committed 25 snapshot rows')):
        res = client.post('/api/snapshot/sync', headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body['status'] == 'ok'
        assert body['rows_upserted'] == 25
        assert body['snapshot_date'] == '2026-09-14'
