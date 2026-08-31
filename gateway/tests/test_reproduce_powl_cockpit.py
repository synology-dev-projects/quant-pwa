import pytest
from app.routers.cockpit import CockpitRequest, get_cockpit_full_payload

def test_cockpit_request_force_refresh_field():
    req = CockpitRequest(ticker='POWL', force_refresh=True)
    assert req.force_refresh is True

@pytest.mark.anyio
async def test_powl_cockpit_payload_with_force_refresh():
    payload = await get_cockpit_full_payload('POWL', force_refresh=True)
    assert payload['status'] == 'ok'
    assert payload['ticker'] == 'POWL'
    gex = payload.get('gex', {})
    assert 'strikes' in gex
    assert len(gex['strikes']) > 0
    assert gex['spot_price'] > 0
