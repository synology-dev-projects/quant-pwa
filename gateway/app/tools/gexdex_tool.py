import time
import httpx
import asyncio
import logging
from datetime import datetime, time as dtime
import pytz
from typing import Dict, Any, Optional, Union, Tuple, List
from app.config import settings
from app.tools.registry import register_tool, emit_tool_ui_event, record_tool_metric

logger = logging.getLogger("quant.gateway")
NY_TZ = pytz.timezone("America/New_York")

# 5-Minute In-Memory SWR (Stale-While-Revalidate) Cache for Benchmark Options
_GEXDEX_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 300.0

BENCHMARK_WARM_TICKERS = [
    "SPY", "QQQ", "IWM", "NVDA", "AAPL", "TSLA", "META", "AMZN", "GOOGL", "MSFT",
    "AMD", "PLTR", "TSM", "SMCI", "COIN", "CRWD", "NFLX", "SPX", "NDX", "RUT"
]

_HTTP_CLIENT = httpx.Client(
    http2=True,
    limits=httpx.Limits(max_keepalive_connections=16, max_connections=32, keepalive_expiry=60.0),
    timeout=35.0
)


def _get_cache_key(tickers: str, max_dte: int, strike_range: int) -> str:
    return f"{tickers}:{max_dte}:{strike_range}"


def _format_dollar_amount(val: Any) -> str:
    """Formats numeric values into compact dollar strings (e.g. +$1.25B, -$450.00M, +$35.20M, $0.00)."""
    if val is None:
        return "$0.00"
    if isinstance(val, str):
        if val.startswith("$") or val.startswith("+$") or val.startswith("-$"):
            return val
        try:
            val = float(val)
        except ValueError:
            return val
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)

    if v == 0:
        return "$0.00"

    sign = "+" if v > 0 else "-"
    abs_v = abs(v)
    if abs_v >= 1_000_000_000:
        return f"{sign}${abs_v / 1_000_000_000:.2f}B"
    elif abs_v >= 1_000_000:
        return f"{sign}${abs_v / 1_000_000:.2f}M"
    elif abs_v >= 1_000:
        return f"{sign}${abs_v / 1_000:.2f}K"
    else:
        return f"{sign}${abs_v:.2f}"


def _format_price(val: Any) -> str:
    """Formats price values to 2 decimal places without leading dollar signs."""
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.2f}"
    except (TypeError, ValueError):
        return str(val).replace("$", "")


def _extract_top_gamma_clusters(item: Dict[str, Any]) -> Tuple[str, str]:
    """Extracts top call and put gamma strikes with formatted exposure values."""
    strikes = []
    if isinstance(item.get("strike_distribution"), dict):
        strikes = item["strike_distribution"].get("strikes", [])
    elif isinstance(item.get("strikes"), list):
        strikes = item["strikes"]

    top_call_str = "N/A"
    top_put_str = "N/A"
    limit = 3

    if isinstance(strikes, list) and strikes:
        call_strikes = [s for s in strikes if isinstance(s, dict) and (s.get("call_gex") or 0) > 0]
        call_strikes.sort(key=lambda s: (s.get("call_gex") or 0), reverse=True)
        top_calls = call_strikes[:limit]

        if top_calls:
            top_call_str = ", ".join(
                f"${_format_price(s.get('strike'))} ({_format_dollar_amount(s.get('call_gex'))})"
                for s in top_calls
            )

        put_strikes = [s for s in strikes if isinstance(s, dict) and abs(s.get("put_gex") or 0) > 0]
        put_strikes.sort(key=lambda s: abs(s.get("put_gex") or 0), reverse=True)
        top_puts = put_strikes[:limit]

        if top_puts:
            top_put_str = ", ".join(
                f"${_format_price(s.get('strike'))} ({_format_dollar_amount(-abs(s.get('put_gex')))})"
                for s in top_puts
            )

    # Fallback to key structural walls if strike list was not available
    if top_call_str == "N/A" and item.get("call_wall") is not None:
        top_call_str = f"${_format_price(item.get('call_wall'))}"
    if top_put_str == "N/A" and item.get("put_wall") is not None:
        top_put_str = f"${_format_price(item.get('put_wall'))}"

    return top_call_str, top_put_str


def _format_single_ticker_summary(item: Dict[str, Any]) -> str:
    """
    Builds the institutional quantitative microstructure summary string for a single ticker.
    Format:
    [QUANTITATIVE MICROSTRUCTURE SUMMARY: {ticker}]
    • Spot Price: ${spot_price} | Regime: {gamma_regime} (Net GEX: {net_gex_formatted})
    • Structural Walls: Call Wall ${call_wall} | Put Wall ${put_wall} | Zero GEX Flip: ${zero_gex_level}
    • Key Gamma Clusters: Calls: {top_call_strikes} | Puts: {top_put_strikes}
    • Market Metrics: Call/Put Ratio: {call_put_ratio} | Net DEX: {net_dex_formatted} | Pin Risk: {pin_risk_level} (Front-Week Concentration: {front_week_pct}%)
    """
    ticker = str(item.get("ticker") or item.get("symbol") or "UNKNOWN").upper()
    spot_price = _format_price(item.get("spot_price"))
    gamma_regime = item.get("gamma_regime") or "Neutral"
    net_gex_formatted = _format_dollar_amount(item.get("net_gex"))

    call_wall = _format_price(item.get("call_wall"))
    put_wall = _format_price(item.get("put_wall"))
    zero_gex_level = _format_price(item.get("zero_gex_level"))

    top_call_strikes, top_put_strikes = _extract_top_gamma_clusters(item)

    cp_val = item.get("call_put_ratio")
    if cp_val is not None:
        try:
            call_put_ratio = f"{float(cp_val):.2f}"
        except (TypeError, ValueError):
            call_put_ratio = str(cp_val)
    else:
        call_put_ratio = "N/A"

    net_dex_formatted = _format_dollar_amount(item.get("net_dex"))
    pin_risk_level = str(item.get("pin_risk_level") or "LOW").upper()

    fw_val = item.get("front_week_gex_pct") if item.get("front_week_gex_pct") is not None else item.get("front_week_pct")
    if fw_val is not None:
        try:
            front_week_pct = f"{float(fw_val):.1f}"
        except (TypeError, ValueError):
            front_week_pct = str(fw_val).replace("%", "")
    else:
        front_week_pct = "0.0"

    summary = (
        f"[QUANTITATIVE MICROSTRUCTURE SUMMARY: {ticker}]\n"
        f"• Spot Price: ${spot_price} | Regime: {gamma_regime} (Net GEX: {net_gex_formatted})\n"
        f"• Structural Walls: Call Wall ${call_wall} | Put Wall ${put_wall} | Zero GEX Flip: ${zero_gex_level}\n"
        f"• Key Gamma Clusters: Calls: {top_call_strikes} | Puts: {top_put_strikes}\n"
        f"• Market Metrics: Call/Put Ratio: {call_put_ratio} | Net DEX: {net_dex_formatted} | Pin Risk: {pin_risk_level} (Front-Week Concentration: {front_week_pct}%)"
    )
    return summary


def _format_gexdex_summary(data: Dict[str, Any]) -> str:
    """Formats full gexdex response payload into clean institutional summaries stripped of massive strike arrays."""
    if not isinstance(data, dict):
        return str(data)

    if "error" in data:
        err_msg = data.get("error", "Unknown error")
        detail = data.get("detail", "")
        ticker = data.get("ticker", "")
        return f"[ERROR: {ticker}] {err_msg} ({detail})" if detail else f"[ERROR: {ticker}] {err_msg}"

    # Handle multi-ticker batch responses
    if "batch_data" in data and isinstance(data["batch_data"], dict) and data["batch_data"]:
        ordered_keys = data.get("tickers") if isinstance(data.get("tickers"), list) else list(data["batch_data"].keys())
        summaries = []
        for sym in ordered_keys:
            sym_item = data["batch_data"].get(sym)
            if isinstance(sym_item, dict):
                summaries.append(_format_single_ticker_summary(sym_item))
        if summaries:
            return "\n\n".join(summaries)

    # Fallback to single-ticker summary
    return _format_single_ticker_summary(data)


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
) -> Union[str, Dict[str, Any]]:
    """
    Queries gexdex-api assistant-summary endpoint with automatic 3x retries and SWR cache fallback.
    Emits full strike distribution to client UI event stream while returning compact quantitative summary string to LLM.
    """
    t0 = time.perf_counter()
    raw_input = tickers or ticker
    if isinstance(raw_input, list):
        clean_tickers = ",".join([t.strip().upper().replace("$", "") for t in raw_input if t.strip()])
    else:
        clean_tickers = ",".join([t.strip().upper().replace("$", "") for t in str(raw_input).split(",") if t.strip()])

    if not clean_tickers:
        record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="MISS", retry_count=0)
        return _format_gexdex_summary({"error": "No valid ticker provided."})

    cache_key = _get_cache_key(clean_tickers, max_dte, strike_range)
    now = time.time()

    # 1. Return fresh in-memory cache if valid and not force_refresh
    if not force_refresh and cache_key in _GEXDEX_MEMORY_CACHE:
        entry = _GEXDEX_MEMORY_CACHE[cache_key]
        if (now - entry["timestamp"]) < CACHE_TTL_SECONDS:
            cached_data = entry["data"]
            # Re-emit UI events for client Canvas charts
            _emit_ui_events_from_payload(cached_data)
            record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="HIT", retry_count=0)
            return _format_gexdex_summary(cached_data)

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
            response = _HTTP_CLIENT.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Clean and emit UI events
                _emit_ui_events_from_payload(data)
                
                # Store in SWR memory cache
                _GEXDEX_MEMORY_CACHE[cache_key] = {
                    "data": data,
                    "timestamp": time.time()
                }
                record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="MISS", retry_count=attempt)
                return _format_gexdex_summary(data)
            elif response.status_code in (502, 503, 504):
                last_error = f"HTTP {response.status_code}"
                time.sleep(0.2 * (2 ** attempt))
                continue
            else:
                record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="MISS", retry_count=attempt)
                return _format_gexdex_summary({
                    "error": f"gexdex-api returned HTTP {response.status_code}",
                    "detail": response.text,
                    "ticker": clean_tickers
                })
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
        stale_data = dict(entry["data"])
        _emit_ui_events_from_payload(stale_data)
        stale_data["_cached_fallback"] = True
        stale_data["_cache_age_seconds"] = stale_age
        record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="HIT", retry_count=3)
        return _format_gexdex_summary(stale_data)

    # 4. Graceful Structured Failure Payload
    record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="MISS", retry_count=3)
    return _format_gexdex_summary({
        "error": "Temporary connectivity delay with options data feed.",
        "detail": f"Upstream microservice did not respond after 3 retry attempts ({last_error}).",
        "ticker": clean_tickers,
        "is_temporary": True
    })


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
    t0 = time.perf_counter()
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
            resp = _HTTP_CLIENT.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="MISS", retry_count=attempt)
                return resp.json()
            elif resp.status_code in (502, 503, 504):
                time.sleep(0.2 * (2 ** attempt))
                continue
            record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="MISS", retry_count=attempt)
            return {"error": f"gexdex-api returned HTTP {resp.status_code}", "ticker": clean_ticker}
        except Exception:
            time.sleep(0.2 * (2 ** attempt))
            continue

    record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="MISS", retry_count=3)
    return {"error": "Failed to fetch strike distribution after 3 retries.", "ticker": clean_ticker}


def is_market_warmer_window(dt: Optional[datetime] = None) -> bool:
    """Checks if current Eastern Time is within market pre-cache window (Mon-Fri 08:30 - 16:15 ET)."""
    if dt is None:
        dt = datetime.now(NY_TZ)
    elif dt.tzinfo is None:
        dt = NY_TZ.localize(dt)
    else:
        dt = dt.astimezone(NY_TZ)

    weekday = dt.weekday()  # 0 = Mon, 4 = Fri, 5 = Sat, 6 = Sun
    if weekday > 4:  # Saturday or Sunday
        return False
    curr_time = dt.time()
    return dtime(8, 30) <= curr_time <= dtime(16, 15)


async def warm_benchmark_cache(force_refresh: bool = False) -> int:
    """
    Calls get_gexdex for individual benchmark tickers in parallel via asyncio.to_thread.
    Logs '[Cache Warmer] Pre-warmed N benchmark tickers in X ms'.
    Returns number of tickers successfully warmed.
    """
    t0 = time.perf_counter()
    tasks = [
        asyncio.to_thread(get_gexdex, ticker=sym, force_refresh=force_refresh)
        for sym in BENCHMARK_WARM_TICKERS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    warmed = 0
    for res in results:
        if isinstance(res, str) and not res.startswith("[ERROR") and "error" not in res.lower():
            warmed += 1
        elif isinstance(res, dict) and "error" not in res:
            warmed += 1

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    logger.info(f"[Cache Warmer] Pre-warmed {warmed} benchmark tickers in {elapsed_ms:.1f} ms")
    return warmed


async def run_cache_warmer_loop(interval_seconds: int = 180):
    """
    Background market hours pre-cache warmer loop.
    Checks if current Eastern Time is within market window (Mon-Fri 08:30 - 16:15 ET).
    If yes, runs warm_benchmark_cache(force_refresh=True).
    Sleeps for interval_seconds using asyncio.sleep().
    Handles cancellation cleanly on server shutdown.
    """
    logger.info(f"🚀 Starting Background Market Hours Pre-Cache Warmer (interval: {interval_seconds}s)")
    try:
        while True:
            try:
                if is_market_warmer_window():
                    await warm_benchmark_cache(force_refresh=True)
            except Exception as e:
                logger.error(f"[Cache Warmer] Error during warm cycle: {e}")
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        logger.info("[Cache Warmer] Background pre-cache warmer stopped gracefully.")
