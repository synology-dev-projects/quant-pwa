import pytest
import time
from unittest.mock import patch, MagicMock
from app.engine.service import (
    CACHE_TTL_SECONDS,
    fetch_raw_data_for_ticker,
    render_gexdex_chart_image,
    _RAW_CACHE,
    _CHART_CACHE,
)


def test_cache_ttl_constant_is_fifteen_minutes():
    """
    Requirement 1: GEX/DEX raw & chart cache TTL must be 15 minutes (900 seconds),
    NOT 1 hour (3600 seconds).
    """
    assert CACHE_TTL_SECONDS == 900.0, f"Expected CACHE_TTL_SECONDS to be 900.0 (15 min), got {CACHE_TTL_SECONDS}"


def test_raw_cache_expires_after_fifteen_minutes():
    """
    Requirement 2: Ensure raw option chain cache expires after 15 minutes (> 900s).
    """
    _RAW_CACHE.clear()
    symbol = "RKLB"
    cache_key = f"{symbol}_50_25"
    now_ts = time.time()

    # Pre-populate cache at 901 seconds ago (older than 15 minutes)
    _RAW_CACHE[cache_key] = (now_ts - 901.0, {"spot_price": 32.50, "mock": "stale"})

    with patch("app.engine.service.extract_raw_data") as mock_extract, \
         patch("app.engine.service.get_shared_config") as mock_conf, \
         patch("app.engine.service.get_shared_session") as mock_sess:
        mock_conf.return_value = MagicMock()
        mock_sess.return_value = MagicMock()
        mock_extract.return_value = {"spot_price": 35.00, "mock": "fresh"}

        res = fetch_raw_data_for_ticker(symbol, max_dte=50, strike_range=25, force_refresh=False)
        assert res is not None
        assert res.get("spot_price") == 35.00
        assert mock_extract.called, "extract_raw_data should have been called when cache > 900s"


def test_raw_cache_force_refresh_bypasses_cache():
    """
    Requirement 3: Ensure force_refresh=True invalidates/bypasses valid cache within 15 min.
    """
    _RAW_CACHE.clear()
    symbol = "RKLB"
    cache_key = f"{symbol}_50_25"
    now_ts = time.time()

    # Pre-populate cache 60s ago (fresh under 15m)
    _RAW_CACHE[cache_key] = (now_ts - 60.0, {"spot_price": 32.50, "mock": "cached"})

    with patch("app.engine.service.extract_raw_data") as mock_extract, \
         patch("app.engine.service.get_shared_config") as mock_conf, \
         patch("app.engine.service.get_shared_session") as mock_sess:
        mock_conf.return_value = MagicMock()
        mock_sess.return_value = MagicMock()
        mock_extract.return_value = {"spot_price": 36.20, "mock": "fresh_force"}

        res = fetch_raw_data_for_ticker(symbol, max_dte=50, strike_range=25, force_refresh=True)
        assert res is not None
        assert res.get("spot_price") == 36.20
        assert mock_extract.called, "extract_raw_data should have been called with force_refresh=True"


def test_chart_cache_force_refresh_bypasses_cache():
    """
    Requirement 4: Ensure render_gexdex_chart_image invalidates cached bytes when force_refresh=True.
    """
    _CHART_CACHE.clear()
    _RAW_CACHE.clear()
    symbol = "RKLB"
    cache_key = f"{symbol}_50_25_webp"
    now_ts = time.time()

    # Pre-populate chart cache 60s ago
    _CHART_CACHE[cache_key] = (now_ts - 60.0, b"OLD_CHART_BYTES")

    with patch("app.engine.service.fetch_raw_data_for_ticker") as mock_fetch, \
         patch("app.engine.service.convert_raw_to_df") as mock_conv, \
         patch("app.engine.service.generate_gexdex_chart") as mock_gen:
        import pandas as pd
        mock_fetch.return_value = {"spot_price": 35.00}
        mock_conv.return_value = pd.DataFrame([{"strike": 35.0}])
        mock_gen.return_value = b"NEW_CHART_BYTES"

        # Without force_refresh -> returns old cached bytes
        cached_result = render_gexdex_chart_image(symbol, max_dte=50, strike_range=25, format="webp", force_refresh=False)
        assert cached_result == b"OLD_CHART_BYTES"

        # With force_refresh -> bypasses cache and returns new chart bytes
        fresh_result = render_gexdex_chart_image(symbol, max_dte=50, strike_range=25, format="webp", force_refresh=True)
        assert fresh_result == b"NEW_CHART_BYTES"
        assert mock_gen.called
