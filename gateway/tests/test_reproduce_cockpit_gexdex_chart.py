import pytest
from unittest.mock import patch
from app.routers.cockpit import get_cockpit_full_payload


@pytest.mark.anyio
async def test_cockpit_gexdex_chart_surfaces_error_when_scraper_fails():
    """
    When live scraper is unavailable or returns empty raw data,
    get_cockpit_full_payload must NOT synthesize fake fallback strikes.
    Instead it must return strikes=[] with explicit error_code, error_message, and error_traceback.
    """
    # Simulate live scraper failure / auth lock
    with patch("app.engine.service.extract_raw_data", return_value=None):
        payload = await get_cockpit_full_payload("SPY", force_refresh=True)

        assert payload["status"] == "ok"
        assert payload["ticker"] == "SPY"

        gex = payload.get("gex", {})
        assert gex.get("strikes") == [], "Synthetic fallback strikes must not be returned when scraper fails"
        assert gex.get("error_code") == "TRADINGEDGE_NO_DATA"
        assert gex.get("error_message")
        assert gex.get("error_traceback")
