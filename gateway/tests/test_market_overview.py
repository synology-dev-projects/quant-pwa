import asyncio
import pytest
from fastapi import HTTPException

from app.core.auth import get_current_user
from app.routers.market_overview import (
    MarketCandleBar,
    compute_intraday_vwap,
    get_market_candles,
    resolve_yahoo_symbol,
    router as market_overview_router,
    _MARKET_CANDLES_CACHE,
)


def test_resolve_yahoo_symbol():
    assert resolve_yahoo_symbol("spx") == "^GSPC"
    assert resolve_yahoo_symbol("NDX") == "^NDX"
    assert resolve_yahoo_symbol("VIX") == "^VIX"
    assert resolve_yahoo_symbol("qqq") == "QQQ"


def test_compute_intraday_vwap():
    bars = [
        MarketCandleBar(timestamp=1, datetime="09:30", open=100.0, high=102.0, low=98.0, close=101.0, volume=100),
        MarketCandleBar(timestamp=2, datetime="09:35", open=101.0, high=105.0, low=100.0, close=104.0, volume=200),
        MarketCandleBar(timestamp=3, datetime="09:40", open=104.0, high=104.0, low=104.0, close=104.0, volume=0),
    ]
    out = compute_intraday_vwap(bars)
    # Bar 1 typical = (102 + 98 + 101) / 3 = 100.3333...
    assert out[0].vwap == pytest.approx(100.33, abs=0.01)
    # Bar 2 typical = (105 + 100 + 104) / 3 = 103.0; cum_pv = 100.3333*100 + 103*200 = 30633.333 / 300 = 102.11
    assert out[1].vwap == pytest.approx(102.11, abs=0.01)
    # Bar 3 has 0 volume, carries forward previous cumulative VWAP
    assert out[2].vwap == pytest.approx(102.11, abs=0.01)


def test_compute_intraday_vwap_all_zero_volume():
    bars = [
        MarketCandleBar(timestamp=1, datetime="09:30", open=15.0, high=15.5, low=14.8, close=15.2, volume=0),
    ]
    out = compute_intraday_vwap(bars)
    assert out[0].vwap is None


def test_market_router_enforces_auth_dependency():
    assert any(d.dependency is get_current_user for d in market_overview_router.dependencies)


def test_market_candles_validation_and_batch(monkeypatch):
    _MARKET_CANDLES_CACHE.clear()

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "chart": {
                    "result": [
                        {
                            "meta": {"chartPreviousClose": 500.0},
                            "timestamp": [1732285800, 1732286100],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [500.0, 502.0],
                                        "high": [503.0, 505.0],
                                        "low": [499.0, 501.0],
                                        "close": [502.0, 504.0],
                                        "volume": [1000, 2000],
                                    }
                                ]
                            },
                        }
                    ]
                }
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            return FakeResp()

    monkeypatch.setattr("app.routers.market_overview.httpx.AsyncClient", FakeAsyncClient)

    body = asyncio.run(get_market_candles(tickers="SPX,QQQ", timeframe="intraday"))
    assert body.status == "ok"
    assert body.timeframe == "intraday"
    assert [r.ticker for r in body.results] == ["SPX", "QQQ"]
    assert body.results[0].yahoo_symbol == "^GSPC"
    assert len(body.results[0].candles) == 2
    assert body.results[0].candles[0].vwap is not None

    with pytest.raises(HTTPException) as exc_tf:
        asyncio.run(get_market_candles(tickers="SPX", timeframe="1w"))
    assert exc_tf.value.status_code == 400

    with pytest.raises(HTTPException) as exc_sym:
        asyncio.run(get_market_candles(tickers="SPX;DROP", timeframe="daily"))
    assert exc_sym.value.status_code == 400
