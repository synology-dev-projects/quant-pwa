import pytest
from unittest.mock import patch
from app.routers.cockpit import get_cockpit_full_payload


@pytest.mark.anyio
async def test_cockpit_gexdex_chart_loads_when_scraper_fails():
    """
    Bug reproduction: Cockpit GEX/DEX chart isn't loading anything when live scraper
    is unavailable or returns empty raw data.
    Expected: get_cockpit_full_payload must provide fallback strike distribution
    and valid spot price so the Interactive Exposure Chart and Key Levels strip load.
    """
    # Simulate live scraper failure / auth lock
    with patch("app.engine.service.extract_raw_data", return_value=None):
        payload = await get_cockpit_full_payload("SPY", force_refresh=True)

        assert payload["status"] == "ok"
        assert payload["ticker"] == "SPY"

        gex = payload.get("gex", {})
        metrics = payload.get("metrics", {})

        # Bug assertion: currently gex['spot_price'] == 0 and gex['strikes'] == []
        assert gex.get("spot_price", 0.0) > 0, "gex.spot_price must be > 0 so key levels load"
        assert metrics.get("spot_price", 0.0) > 0, "metrics.spot_price must be > 0"

        strikes = gex.get("strikes", [])
        assert isinstance(strikes, list)
        assert len(strikes) > 0, "gex.strikes must contain strike distribution for chart rendering"

        first_strike = strikes[0]
        assert "strike" in first_strike
        assert "call_gex" in first_strike
        assert "put_gex" in first_strike
        assert "net_gex" in first_strike
