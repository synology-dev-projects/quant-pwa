import time
import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, Tuple, List, Union
import pandas as pd

from app.tools.registry import register_tool, record_tool_metric

logger = logging.getLogger("quant.gateway.tools.flow")

_FLOW_MEMORY_CACHE: Dict[str, Tuple[float, str]] = {}
CACHE_TTL_SECONDS = 300
MAX_FLOW_CACHE_ENTRIES = 1024


def _store_flow_cache(cache_key: str, summary: str) -> None:
    """Stores summary in memory cache with bounded capacity eviction."""
    if len(_FLOW_MEMORY_CACHE) >= MAX_FLOW_CACHE_ENTRIES:
        sorted_keys = sorted(_FLOW_MEMORY_CACHE.keys(), key=lambda k: _FLOW_MEMORY_CACHE[k][0])
        for k in sorted_keys[:max(1, MAX_FLOW_CACHE_ENTRIES // 5)]:
            _FLOW_MEMORY_CACHE.pop(k, None)
    _FLOW_MEMORY_CACHE[cache_key] = (time.time(), summary)


def _format_dollar_amount(val: Any) -> str:
    """Formats numeric values into compact dollar strings (e.g. $14.20M, $780.00K, $1.85B, $0.00)."""
    if val is None:
        return "$0.00"
    if isinstance(val, str):
        if val.startswith("$"):
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

    abs_v = abs(v)
    sign = "-" if v < 0 else ""
    if abs_v >= 1_000_000_000:
        return f"{sign}${abs_v / 1_000_000_000:.2f}B"
    elif abs_v >= 1_000_000:
        return f"{sign}${abs_v / 1_000_000:.2f}M"
    elif abs_v >= 1_000:
        return f"{sign}${abs_v / 1_000:.2f}K"
    return f"{sign}${abs_v:.2f}"


def _format_single_flow_summary(symbol: str, df: Optional[pd.DataFrame], lookback_days: int) -> str:
    """Formats raw flow rows into a high-density institutional markdown briefing (~100 tokens)."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return f"[INSTITUTIONAL UNUSUAL OPTIONS FLOW: {symbol}] No unusual institutional options flow recorded in the past {lookback_days} days."

    # Compute aggregates
    total_records = len(df)
    call_df = df[df["ORDER_TYPE"].str.contains("CALL", case=False, na=False)] if "ORDER_TYPE" in df.columns else pd.DataFrame()
    put_df = df[df["ORDER_TYPE"].str.contains("PUT", case=False, na=False)] if "ORDER_TYPE" in df.columns else pd.DataFrame()

    call_premium = float(call_df["PREMIUM"].sum()) if not call_df.empty and "PREMIUM" in call_df.columns else 0.0
    put_premium = float(put_df["PREMIUM"].sum()) if not put_df.empty and "PREMIUM" in put_df.columns else 0.0
    total_premium = call_premium + put_premium

    call_pct = (call_premium / total_premium * 100.0) if total_premium > 0 else 0.0
    put_pct = (put_premium / total_premium * 100.0) if total_premium > 0 else 0.0

    # Net Score & Sentiment
    net_score_val = None
    if "NET_SCORE" in df.columns and pd.notna(df["NET_SCORE"].iloc[0]):
        net_score_val = float(df["NET_SCORE"].iloc[0])

    if net_score_val is not None:
        net_score_str = f"{net_score_val:+.1f}" if net_score_val != 0 else "0.0"
        if net_score_val > 0:
            sentiment_str = "Bullish"
        elif net_score_val < 0:
            sentiment_str = "Bearish"
        else:
            sentiment_str = "Neutral"
    else:
        net_score_str = "N/A"
        if call_pct >= 65:
            sentiment_str = "Heavily Bullish"
        elif call_pct >= 55:
            sentiment_str = "Moderately Bullish"
        elif put_pct >= 65:
            sentiment_str = "Heavily Bearish"
        elif put_pct >= 55:
            sentiment_str = "Moderately Bearish"
        else:
            sentiment_str = "Neutral"

    # Top high-conviction prints (up to 5)
    sorted_df = df.sort_values(by=["PREMIUM", "TRADE_DATE"], ascending=[False, False]) if "PREMIUM" in df.columns else df
    top_prints = sorted_df.head(5)

    print_lines = []
    for _, row in top_prints.iterrows():
        t_date = str(row.get("TRADE_DATE", ""))[:10]
        o_type = str(row.get("ORDER_TYPE", "")).replace("_", " ").upper()
        strike = row.get("STRIKE_PRICE", "N/A")
        try:
            strike_fmt = f"${float(strike):.2f}"
        except Exception:
            strike_fmt = f"${strike}"
            
        otm = row.get("STRIKE_OTM_PCT")
        exp = str(row.get("EXPIRATION_DATE", ""))[:10]
        prem = _format_dollar_amount(row.get("PREMIUM", 0))
        oi = row.get("OPEN_INTEREST", "N/A")
        try:
            oi_fmt = f"{int(oi):,}"
        except Exception:
            oi_fmt = str(oi)
            
        unusual_flag = " ⚠️" if row.get("IS_UNUSUAL_OI") in [1, True, "1"] else ""
        otm_str = f" ({otm:+.1f}%)" if pd.notna(otm) and isinstance(otm, (int, float)) else ""
        print_lines.append(f"  • {t_date}: {prem} {o_type} | Strike: {strike_fmt}{otm_str} | Exp: {exp} | OI: {oi_fmt}{unusual_flag}")

    prints_block = "\n".join(print_lines) if print_lines else "  • None"

    header = f"[INSTITUTIONAL UNUSUAL OPTIONS FLOW: {symbol} (Last {lookback_days} Days)]"
    volume_line = f"• Total Net Flow Volume: {_format_dollar_amount(total_premium)} (Call Flow: {_format_dollar_amount(call_premium)} [{call_pct:.1f}%] | Put Flow: {_format_dollar_amount(put_premium)} [{put_pct:.1f}%])"
    sentiment_line = f"• Flow Sentiment Score: {net_score_str} | Sentiment: {sentiment_str}"
    prints_header = "• High-Conviction Prints:"

    return f"{header}\n{volume_line}\n{sentiment_line}\n{prints_header}\n{prints_block}"


@register_tool(
    name="get_unusual_flow",
    description=(
        "Retrieves institutional unusual options flow, smart money blocks, aggressive sweeps, "
        "and volume-to-open-interest anomalies for a given ticker symbol over a lookback window (default 30 days). "
        "Use this tool when users inquire about options flow, whale trades, big money positioning, sweeps, or unusual volume."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock or ETF ticker symbol (e.g. 'NVDA', 'SPY', 'PLTR', or comma-separated list like 'AAPL,MSFT')"
            },
            "lookback_days": {
                "type": "integer",
                "description": "Number of days to look back for unusual flow prints (default: 30)"
            },
            "min_premium": {
                "type": "number",
                "description": "Minimum premium threshold in USD to filter flow prints (default: 0.0)"
            }
        },
        "required": ["ticker"]
    }
)
def get_unusual_flow(
    ticker: str = "",
    lookback_days: int = 30,
    min_premium: float = 0.0,
    force_refresh: bool = False
) -> str:
    """
    Queries institutional unusual options flow from Oracle DB via common_lib.
    Executes multi-ticker batch queries in a single flight.
    Guarded by SWR in-memory cache (300s TTL), live scrape fallback, and fault isolation.
    """
    t0 = time.perf_counter()
    raw_tickers = [t.strip().upper().replace("$", "") for t in str(ticker).split(",") if t.strip()]
    
    # Deduplicate while preserving order
    seen = set()
    clean_tickers = []
    for t in raw_tickers:
        if t not in seen:
            seen.add(t)
            clean_tickers.append(t)

    if not clean_tickers:
        record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="MISS", retry_count=0)
        return "[INSTITUTIONAL UNUSUAL OPTIONS FLOW] No valid ticker provided."

    cached_summaries: Dict[str, str] = {}
    missing_tickers: List[str] = []
    now = time.time()

    for sym in clean_tickers:
        cache_key = f"{sym}:{lookback_days}:{min_premium}"
        if not force_refresh and cache_key in _FLOW_MEMORY_CACHE:
            ts, cached_summary = _FLOW_MEMORY_CACHE[cache_key]
            if now - ts < CACHE_TTL_SECONDS:
                cached_summaries[sym] = cached_summary
                continue
        missing_tickers.append(sym)

    if missing_tickers:
        df_all = pd.DataFrame()
        config = None
        try:
            from common_lib.config.main_config import load_config

            config = load_config()
            db_type = getattr(config, "db_type", "postgres").lower()

            if db_type == "postgres":
                from common_lib.connectors.postgres import get_unusual_flow as pg_get_flow
                df_all = pg_get_flow(
                    config=config,
                    symbols=missing_tickers,
                    lookback_days=lookback_days,
                    min_premium=min_premium
                )
            else:
                from common_lib.connectors.oracle import get_unusual_flow as oracle_get_flow
                df_all = oracle_get_flow(
                    config=config,
                    symbols=missing_tickers,
                    lookback_days=lookback_days,
                    min_premium=min_premium
                )
        except Exception as ex:
            logger.warning(f"Failed to query DB for batch unusual flow ({missing_tickers}): {ex}")
            df_all = pd.DataFrame()

        for sym in missing_tickers:
            cache_key = f"{sym}:{lookback_days}:{min_premium}"
            if not df_all.empty and "SYMBOL" in df_all.columns:
                df_sym = df_all[df_all["SYMBOL"].str.upper() == sym]
            else:
                df_sym = pd.DataFrame()

            if df_sym.empty:
                # Optionally attempt an in-process live scrape fallback via extract_flow_for_symbol
                try:
                    import sys
                    from pathlib import Path
                    pipeline_dir = Path(__file__).resolve().parents[3] / "unusual-option-flow-pipeline"
                    if pipeline_dir.exists() and str(pipeline_dir) not in sys.path:
                        sys.path.insert(0, str(pipeline_dir))

                    from src.extract import extract_flow_for_symbol
                    from src.transform import transform_flow_records

                    if config is None:
                        from common_lib.config.main_config import load_config
                        config = load_config()

                    live_records = extract_flow_for_symbol(config=config, symbol=sym)
                    if live_records:
                        df_live = transform_flow_records(live_records)
                        if not df_live.empty:
                            df_live.columns = df_live.columns.str.upper()
                            df_sym = df_live
                except Exception as fallback_err:
                    logger.debug(f"Live flow fallback attempt for {sym} skipped or failed: {fallback_err}")

            sym_summary = _format_single_flow_summary(sym, df_sym, lookback_days)
            _store_flow_cache(cache_key, sym_summary)
            cached_summaries[sym] = sym_summary

    cache_status = "HIT" if not missing_tickers else "MISS"
    record_tool_metric(
        latency_ms=(time.perf_counter() - t0) * 1000.0,
        cache_status=cache_status,
        retry_count=0
    )

    summaries = [cached_summaries[sym] for sym in clean_tickers if sym in cached_summaries]
    return "\n\n".join(summaries)
