"""
gateway/app/core/quote_feed.py - Real-Time Free Spot Price & Quote Engine
Provides async batch quote retrieval with 4-second in-memory caching.
Zero external API keys or subscriptions required.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("quant.gateway.quotes")

_QUOTE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
CACHE_TTL = 4.0


class QuoteItem(BaseModel):
    ticker: str
    price: float
    change: float = 0.0
    change_pct: float = 0.0
    prev_close: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    updated_at: str
    is_stale: bool = False


class WatchlistQuotesResponse(BaseModel):
    watchlist_id: str
    updated_at: str
    quotes: Dict[str, QuoteItem] = Field(default_factory=dict)


def clear_quote_cache() -> None:
    global _QUOTE_CACHE
    _QUOTE_CACHE.clear()


async def fetch_single_quote(client: httpx.AsyncClient, ticker: str) -> Optional[Dict[str, Any]]:
    clean_sym = ticker.strip().upper().replace("$", "")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_sym}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        resp = await client.get(url, headers=headers, timeout=3.5)
        if resp.status_code != 200:
            logger.warning(f"[QuoteFeed] Failed to fetch quote for {clean_sym}: HTTP {resp.status_code}")
            return None

        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None

        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose") or price

        if price is None:
            return None

        p_float = float(price)
        prev_float = float(prev_close) if prev_close else p_float
        change = round(p_float - prev_float, 4)
        change_pct = round((change / prev_float) * 100, 2) if prev_float > 0 else 0.0

        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "ticker": clean_sym,
            "price": round(p_float, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "prev_close": round(prev_float, 2) if prev_float else None,
            "day_high": round(float(meta["regularMarketDayHigh"]), 2) if meta.get("regularMarketDayHigh") is not None else None,
            "day_low": round(float(meta["regularMarketDayLow"]), 2) if meta.get("regularMarketDayLow") is not None else None,
            "updated_at": now_iso,
            "is_stale": False
        }
    except Exception as ex:
        logger.warning(f"[QuoteFeed] Exception fetching quote for {clean_sym}: {ex}")
        return None


async def get_batch_quotes(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    clean_tickers = list(dict.fromkeys([t.strip().upper() for t in tickers if t.strip()]))
    now = time.time()
    quotes: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []

    for t in clean_tickers:
        if t in _QUOTE_CACHE:
            ts, item = _QUOTE_CACHE[t]
            if now - ts < CACHE_TTL:
                quotes[t] = item
                continue
        missing.append(t)

    if missing:
        async with httpx.AsyncClient(timeout=3.5) as client:
            tasks = [fetch_single_quote(client, t) for t in missing]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for t, res in zip(missing, results):
                if isinstance(res, dict) and res is not None:
                    _QUOTE_CACHE[t] = (now, res)
                    quotes[t] = res
                elif t in _QUOTE_CACHE:
                    # Serve stale fallback if network blipped
                    _, stale_item = _QUOTE_CACHE[t]
                    stale_copy = dict(stale_item)
                    stale_copy["is_stale"] = True
                    quotes[t] = stale_copy

    return quotes
