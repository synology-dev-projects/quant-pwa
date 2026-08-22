import time
import httpx
import logging
from typing import Dict, Any, Optional
from app.config import settings
from app.tools.registry import register_tool, emit_tool_ui_event

# 60-Second In-Memory SWR (Stale-While-Revalidate) Cache
_GEXDEX_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 60.0


def _get_cache_key(tickers: str, max_dte: int, strike_range: int) -> str:
    return f"{tickers}:{max_dte}:{strike_range}"


@register_tool(
    name="get_gexdex",
    description="Fetch proprietary institutional options Gamma Exposure (GEX) and Delta Exposure (DEX) analytics for one or more stock ticker symbols (e.g. AAPL, TSLA, NVDA, SPY, QQQ). Accepts single tickers or comma-separated ticker lists. Returns spot price, net GEX/DEX, zero gamma flip level, key call/put walls, and full strike distributions.",
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol or comma-separated list (e.g. AAPL or AAPL,TSLA,SPY)"
            },
            "tickers": {
                "type": "string",
                "description": "Optional comma-separated list of stock ticker symbols"
            },
            "max_dte": {
                "type": "integer",
                "description": "Maximum days to expiration to include in the options calculation (default: 50)"
            },
            "strike_range": {
                "type": "integer",
                "description": "Number of strikes above/below the current spot price to evaluate (default: 25)"
            },
            "force_refresh": {
                "type": "boolean",
                "description": "Force live fetch bypassing cache (default: False)"
            }
        },
        "required": ["ticker"]
    }
)
def get_gexdex(
    ticker: str = "",
    max_dte: int = 50,
    strike_range: int = 25,
    force_refresh: bool = False,
    tickers: Optional[str] = None
) -> Dict[str, Any]:
    """
    Queries gexdex-api assistant-summary endpoint with automatic 3x retries and SWR cache fallback.
    """
    raw_input = tickers or ticker
    if isinstance(raw_input, list):
        clean_tickers = ",".join([t.strip().upper().replace("$", "") for t in raw_input if t.strip()])
    else:
        clean_tickers = ",".join([t.strip().upper().replace("$", "") for t in str(raw_input).split(",") if t.strip()])

    if not clean_tickers:
        return {"error": "No valid ticker provided."}

    cache_key = _get_cache_key(clean_tickers, max_dte, strike_range)
    now = time.time()

    # 1. Return fresh in-memory cache if valid and not force_refresh
    if not force_refresh and cache_key in _GEXDEX_MEMORY_CACHE:
        entry = _GEXDEX_MEMORY_CACHE[cache_key]
        if (now - entry["timestamp"]) < CACHE_TTL_SECONDS:
            cached_data = entry["data"]
            # Re-emit UI events for client Canvas charts
            _emit_ui_events_from_payload(cached_data)
            return cached_data

    url = f"{settings.GEXDEX_API_URL.rstrip('/')}/api/v1/gexdex/assistant-summary"
    params = {
        "tickers": clean_tickers,
        "max_dte": max_dte,
        "strike_range": strike_range,
        "force_refresh": str(force_refresh).lower()
    }
    headers = {
        "X-API-Key": settings.GEXDEX_API_KEY
    }

    # 2. Transparent 3-attempt retry loop with exponential backoff
    last_error = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url, params=params, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Clean and emit UI events
                    _emit_ui_events_from_payload(data)
                    
                    # Store in SWR memory cache
                    _GEXDEX_MEMORY_CACHE[cache_key] = {
                        "data": data,
                        "timestamp": time.time()
                    }
                    return data
                elif response.status_code in (502, 503, 504):
                    last_error = f"HTTP {response.status_code}"
                    time.sleep(0.2 * (2 ** attempt))
                    continue
                else:
                    return {
                        "error": f"gexdex-api returned HTTP {response.status_code}",
                        "detail": response.text,
                        "ticker": clean_tickers
                    }
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as net_err:
            last_error = str(net_err)
            time.sleep(0.2 * (2 ** attempt))
            continue
        except Exception as e:
            last_error = str(e)
            break

    # 3. SWR Cache Fallback: If live query failed after 3 attempts, serve stale cached data
    if cache_key in _GEXDEX_MEMORY_CACHE:
        entry = _GEXDEX_MEMORY_CACHE[cache_key]
        stale_age = int(time.time() - entry["timestamp"])
        logging.warning(f"Serving stale GEXDEX cache for {clean_tickers} ({stale_age}s old) due to upstream error: {last_error}")
        stale_data = entry["data"]
        _emit_ui_events_from_payload(stale_data)
        stale_data["_cached_fallback"] = True
        stale_data["_cache_age_seconds"] = stale_age
        return stale_data

    # 4. Graceful Structured Failure Payload
    return {
        "error": "Temporary connectivity delay with options data feed.",
        "detail": f"Upstream microservice did not respond after 3 retry attempts ({last_error}).",
        "ticker": clean_tickers,
        "is_temporary": True
    }


def _clean_image_references(obj: Any) -> Any:
    """Recursively removes chart.png, markdown image fields, and image URLs from dictionaries and lists."""
    if isinstance(obj, dict):
        image_keys = {
            "markdown_image", "chart_png_url", "chart_url", "image_url",
            "image", "chart_png", "chart_image", "chart_webp_url"
        }
        for k in list(obj.keys()):
            val = obj[k]
            if k.lower() in image_keys or (isinstance(val, str) and ("chart.png" in val or "![chart]" in val or "![options" in val.lower())):
                obj.pop(k, None)
            else:
                _clean_image_references(val)
    elif isinstance(obj, list):
        for item in obj:
            _clean_image_references(item)
    return obj


def _emit_ui_events_from_payload(data: Dict[str, Any]) -> None:
    """
    Emits strike distribution UI events for client-side HTML5 Canvas rendering
    and completely strips any server /chart.png or markdown image references.
    """
    if not isinstance(data, dict):
        return

    # Strip image references recursively across the payload
    _clean_image_references(data)

    # Emit tool UI events for batch or single payload
    if "batch_data" in data and isinstance(data["batch_data"], dict):
        for sym, item in data["batch_data"].items():
            if isinstance(item, dict) and "strike_distribution" in item and item["strike_distribution"]:
                emit_tool_ui_event("get_gexdex", item["strike_distribution"])
    else:
        if "strike_distribution" in data and data["strike_distribution"]:
            emit_tool_ui_event("get_gexdex", data["strike_distribution"])


@register_tool(
    name="get_strike_distribution",
    description="Fetch granular strike-level GEX and DEX distribution with multi-expiration breakdowns for a single ticker.",
    parameters={
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol (e.g. SPY, NVDA)"},
            "strike_range": {"type": "integer", "description": "Number of strikes above/below spot (default: 25)"},
            "max_dte": {"type": "integer", "description": "Maximum DTE (default: 50)"},
            "force_refresh": {"type": "boolean", "description": "Bypass cache"}
        },
        "required": ["ticker"]
    }
)
def get_strike_distribution(
    ticker: str = "SPY",
    strike_range: int = 25,
    max_dte: int = 50,
    force_refresh: bool = False
) -> Dict[str, Any]:
    clean_ticker = ticker.strip().upper().replace("$", "")
    url = f"{settings.GEXDEX_API_URL.rstrip('/')}/api/v1/gexdex/strikes"
    params = {
        "ticker": clean_ticker,
        "strike_range": strike_range,
        "max_dte": max_dte,
        "force_refresh": str(force_refresh).lower()
    }
    headers = {"X-API-Key": settings.GEXDEX_API_KEY}
    
    for attempt in range(3):
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code in (502, 503, 504):
                    time.sleep(0.2 * (2 ** attempt))
                    continue
                return {"error": f"gexdex-api returned HTTP {resp.status_code}", "ticker": clean_ticker}
        except Exception:
            time.sleep(0.2 * (2 ** attempt))
            continue

    return {"error": "Failed to fetch strike distribution after 3 retries.", "ticker": clean_ticker}
