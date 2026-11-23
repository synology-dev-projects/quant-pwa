import asyncio
import logging
import re
import time as time_module
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Market Overview"], dependencies=[Depends(get_current_user)])

_TICKER_RE = re.compile(r"^[A-Za-z0-9^.=_-]{1,12}$")

_SYMBOL_MAP: Dict[str, str] = {
    "SPX": "^GSPC",
    "NDX": "^NDX",
    "VIX": "^VIX",
    "DJI": "^DJI",
    "RUT": "^RUT",
}

_MARKET_CANDLES_CACHE: Dict[str, Tuple[float, "TickerCandlesResult"]] = {}


class MarketCandleBar(BaseModel):
    timestamp: int
    datetime: str
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    vwap: Optional[float] = None


class TickerCandlesResult(BaseModel):
    ticker: str
    yahoo_symbol: str
    timeframe: str
    as_of_date: str = ""
    spot_price: Optional[float] = None
    session_open: Optional[float] = None
    session_close: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    session_change_pts: Optional[float] = None
    session_change_pct: Optional[float] = None
    candles: List[MarketCandleBar] = []
    message: Optional[str] = None


class MarketCandlesBatchResponse(BaseModel):
    status: str
    timeframe: str
    results: List[TickerCandlesResult] = []


def resolve_yahoo_symbol(ticker: str) -> str:
    clean = ticker.strip().upper()
    return _SYMBOL_MAP.get(clean, clean)


def compute_intraday_vwap(bars: List[MarketCandleBar]) -> List[MarketCandleBar]:
    """Compute cumulative intraday VWAP across bars where volume > 0."""
    cum_pv = 0.0
    cum_vol = 0
    for bar in bars:
        if bar.volume > 0:
            typical_price = (bar.high + bar.low + bar.close) / 3.0
            cum_pv += typical_price * bar.volume
            cum_vol += bar.volume
            bar.vwap = round(cum_pv / cum_vol, 2)
        elif cum_vol > 0:
            bar.vwap = round(cum_pv / cum_vol, 2)
        else:
            bar.vwap = None
    return bars


def _compute_metrics(bars: List[MarketCandleBar], prev_close: Optional[float] = None) -> Dict[str, Optional[float]]:
    if not bars:
        return {
            "spot_price": None,
            "session_open": None,
            "session_close": None,
            "session_high": None,
            "session_low": None,
            "session_change_pts": None,
            "session_change_pct": None,
        }
    s_open = bars[0].open
    s_close = bars[-1].close
    s_high = max(b.high for b in bars)
    s_low = min(b.low for b in bars)
    ref = prev_close if (prev_close is not None and prev_close > 0) else s_open
    pts = round(s_close - ref, 2) if ref else None
    pct = round((pts / ref) * 100.0, 2) if (pts is not None and ref) else None
    return {
        "spot_price": s_close,
        "session_open": s_open,
        "session_close": s_close,
        "session_high": s_high,
        "session_low": s_low,
        "session_change_pts": pts,
        "session_change_pct": pct,
    }


async def _fetch_ticker_candles(ticker: str, timeframe: str) -> TickerCandlesResult:
    clean_ticker = ticker.strip().upper()
    yahoo_sym = resolve_yahoo_symbol(clean_ticker)
    cache_key = f"{clean_ticker}:{timeframe}"
    ttl = 30.0 if timeframe == "intraday" else 300.0

    if cache_key in _MARKET_CANDLES_CACHE:
        cached_at, cached_res = _MARKET_CANDLES_CACHE[cache_key]
        if time_module.time() - cached_at < ttl:
            return cached_res

    encoded_sym = quote(yahoo_sym, safe="")
    if timeframe == "daily":
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_sym}?range=6mo&interval=1d"
    else:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_sym}?range=5d&interval=5m"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    eastern = ZoneInfo("America/New_York")
    bars: List[MarketCandleBar] = []
    prev_close: Optional[float] = None
    as_of_date = ""
    message: Optional[str] = None

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("chart", {}).get("result", [])
                if results:
                    res0 = results[0]
                    meta = res0.get("meta", {})
                    raw_prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                    if raw_prev is not None:
                        prev_close = float(raw_prev)

                    timestamps = res0.get("timestamp", [])
                    indicators = res0.get("indicators", {}).get("quote", [{}])[0]
                    opens = indicators.get("open", [])
                    highs = indicators.get("high", [])
                    lows = indicators.get("low", [])
                    closes = indicators.get("close", [])
                    volumes = indicators.get("volume", [])

                    raw_entries = []
                    for i, ts in enumerate(timestamps):
                        if i >= len(opens) or i >= len(highs) or i >= len(lows) or i >= len(closes):
                            break
                        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
                        if o is None or h is None or l is None or c is None:
                            continue
                        bar_dt = datetime.fromtimestamp(ts, eastern)
                        vol = int(volumes[i]) if (i < len(volumes) and volumes[i] is not None) else 0
                        raw_entries.append((ts, bar_dt, float(o), float(h), float(l), float(c), vol))

                    if timeframe == "intraday" and raw_entries:
                        # Filter to RTH (09:30 - 16:15 ET) and select the latest active session date
                        rth_entries = [
                            e for e in raw_entries
                            if time(9, 30) <= e[1].time() <= time(16, 15)
                        ]
                        target_entries = rth_entries if rth_entries else raw_entries
                        latest_date = target_entries[-1][1].date()
                        as_of_date = latest_date.strftime("%Y-%m-%d")
                        session_entries = [e for e in target_entries if e[1].date() == latest_date]

                        # Previous session close for accurate intraday % change
                        prior_entries = [e for e in target_entries if e[1].date() < latest_date]
                        if prior_entries:
                            prev_close = prior_entries[-1][5]

                        for ts, bar_dt, o, h, l, c, vol in session_entries:
                            bars.append(MarketCandleBar(
                                timestamp=ts,
                                datetime=bar_dt.strftime("%H:%M"),
                                open=round(o, 2),
                                high=round(h, 2),
                                low=round(l, 2),
                                close=round(c, 2),
                                volume=vol,
                            ))
                        compute_intraday_vwap(bars)
                    elif timeframe == "daily" and raw_entries:
                        as_of_date = raw_entries[-1][1].strftime("%Y-%m-%d")
                        for ts, bar_dt, o, h, l, c, vol in raw_entries:
                            bars.append(MarketCandleBar(
                                timestamp=ts,
                                datetime=bar_dt.strftime("%Y-%m-%d"),
                                open=round(o, 2),
                                high=round(h, 2),
                                low=round(l, 2),
                                close=round(c, 2),
                                volume=vol,
                                vwap=None,
                            ))
                        if len(bars) >= 2:
                            prev_close = bars[-2].close
                else:
                    message = f"No market data returned for {clean_ticker}."
            else:
                message = f"Upstream quote status {resp.status_code} for {clean_ticker}."
    except (httpx.TimeoutException, httpx.RequestError) as ex:
        logger.warning(f"Error fetching {timeframe} candles for {clean_ticker}: {ex}")
        message = f"Failed to fetch {clean_ticker} data."

    metrics = _compute_metrics(bars, prev_close=prev_close)
    result = TickerCandlesResult(
        ticker=clean_ticker,
        yahoo_symbol=yahoo_sym,
        timeframe=timeframe,
        as_of_date=as_of_date,
        candles=bars,
        message=message if not bars else None,
        **metrics,
    )
    _MARKET_CANDLES_CACHE[cache_key] = (time_module.time(), result)
    return result


@router.get("/candles", response_model=MarketCandlesBatchResponse)
async def get_market_candles(
    tickers: str = Query("SPX,NDX,VIX,QQQ", description="Comma-separated ticker symbols (max 12)"),
    timeframe: str = Query("intraday", description="Chart timeframe: 'intraday' or 'daily'"),
):
    tf = timeframe.strip().lower()
    if tf not in ("intraday", "daily"):
        raise HTTPException(status_code=400, detail="timeframe must be 'intraday' or 'daily'")

    raw_tickers = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not raw_tickers:
        raise HTTPException(status_code=400, detail="At least one ticker is required")
    if len(raw_tickers) > 12:
        raise HTTPException(status_code=400, detail="Maximum 12 tickers per request")

    seen = set()
    clean_tickers: List[str] = []
    for t in raw_tickers:
        if not _TICKER_RE.match(t):
            raise HTTPException(status_code=400, detail=f"Invalid ticker symbol: {t}")
        if t not in seen:
            seen.add(t)
            clean_tickers.append(t)

    results = await asyncio.gather(*(_fetch_ticker_candles(t, tf) for t in clean_tickers))
    return MarketCandlesBatchResponse(status="ok", timeframe=tf, results=list(results))
