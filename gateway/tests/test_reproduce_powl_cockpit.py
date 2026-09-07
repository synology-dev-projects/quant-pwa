import pytest
from app.routers.cockpit import CockpitRequest, get_cockpit_full_payload

def test_cockpit_request_force_refresh_field():
    req = CockpitRequest(ticker='POWL', force_refresh=True)
    assert req.force_refresh is True

@pytest.mark.anyio
async def test_powl_cockpit_payload_with_force_refresh():
    from unittest.mock import patch
    from app.engine.service import StrikeDistributionResponse, StrikeDetail
    
    mock_dist = StrikeDistributionResponse(
        ticker='POWL',
        spot_price=179.73,
        call_wall=190.0,
        put_wall=170.0,
        zero_gex_level=175.0,
        gamma_centroid=180.0,
        call_put_ratio=1.2,
        gamma_regime='Long Gamma',
        net_gex=1000000.0,
        net_dex=500000.0,
        expirations=['2026-09-18'],
        strikes=[
            StrikeDetail(strike=170.0, call_gex=100000.0, put_gex=-500000.0, call_dex=50000.0, put_dex=-200000.0, net_gex=-400000.0, net_dex=-150000.0),
            StrikeDetail(strike=180.0, call_gex=800000.0, put_gex=-200000.0, call_dex=400000.0, put_dex=-100000.0, net_gex=600000.0, net_dex=300000.0),
            StrikeDetail(strike=190.0, call_gex=1500000.0, put_gex=-50000.0, call_dex=800000.0, put_dex=-30000.0, net_gex=1450000.0, net_dex=770000.0)
        ],
        updated_at='2026-09-07T14:00:00Z'
    )
    with patch('app.routers.cockpit.get_strike_distribution', return_value=mock_dist):
        payload = await get_cockpit_full_payload('POWL', force_refresh=True)
        assert payload['status'] == 'ok'
        assert payload['ticker'] == 'POWL'
        gex = payload.get('gex', {})
        assert 'strikes' in gex
        assert len(gex['strikes']) > 0
        assert gex['spot_price'] > 0
