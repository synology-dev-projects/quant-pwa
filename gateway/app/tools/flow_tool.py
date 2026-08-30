import re
import time
import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, Tuple, List, Union
from contextvars import ContextVar
import pandas as pd

from app.tools.registry import register_tool, record_tool_metric

import threading

logger = logging.getLogger("quant.gateway.tools.flow")

_FLOW_CACHE_LOCK = threading.Lock()
_FLOW_MEMORY_CACHE: Dict[str, Tuple[float, str]] = {}
_LAST_EXECUTED_FLOW_RESULT: Dict[str, Tuple[float, str]] = {}
CACHE_TTL_SECONDS = 300
MAX_FLOW_CACHE_ENTRIES = 1024


def get_last_flow_table() -> Optional[str]:
    """Returns the most recently executed flow table result across threads (within 30s window)."""
    now = time.time()
    with _FLOW_CACHE_LOCK:
        if _LAST_EXECUTED_FLOW_RESULT:
            latest_key = max(_LAST_EXECUTED_FLOW_RESULT.keys(), key=lambda k: _LAST_EXECUTED_FLOW_RESULT[k][0])
            ts, table = _LAST_EXECUTED_FLOW_RESULT[latest_key]
            if now - ts < 30.0:
                return table
    return None


def clear_flow_cache() -> int:
    """
    Thread-safely clears all in-memory options flow caches and returns count of evicted entries.
    """
    with _FLOW_CACHE_LOCK:
        count = len(_FLOW_MEMORY_CACHE) + len(_LAST_EXECUTED_FLOW_RESULT)
        _FLOW_MEMORY_CACHE.clear()
        _LAST_EXECUTED_FLOW_RESULT.clear()
    logger.info(f"Cleared {count} entries from Options Flow in-memory cache.")
    return count


def _store_flow_cache(cache_key: str, summary: str) -> None:
    """Stores summary in memory cache with bounded capacity eviction and thread synchronization."""
    with _FLOW_CACHE_LOCK:
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


DATE_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{1,2}/\d{1,2}(?:/\d{2,4})?$"),
]
MARKET_DATE_KEYWORDS = {
    "YESTERDAY", "TODAY", "LATEST", "MARKET", "ALL", 
    "FRIDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
    "LAST FRIDAY", "THIS FRIDAY"
}


def format_market_wide_flow_summary(df: Optional[pd.DataFrame], target_date_str: str) -> str:
    """Formats market-wide unusual options flow for a specific trade date into a Macro-First institutional summary."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return f"[MARKET-WIDE UNUSUAL OPTIONS FLOW: {target_date_str}] No qualifying institutional options flow recorded for this trading date."

    # Identify actual date if available
    display_date = target_date_str
    if "TRADE_DATE" in df.columns and pd.notna(df["TRADE_DATE"].iloc[0]):
        display_date = str(df["TRADE_DATE"].iloc[0])[:10]

    total_premium = float(df["PREMIUM"].sum()) if "PREMIUM" in df.columns else 0.0

    call_df = df[df["ORDER_TYPE"].str.contains("CALL", case=False, na=False)] if "ORDER_TYPE" in df.columns else pd.DataFrame()
    put_df = df[df["ORDER_TYPE"].str.contains("PUT", case=False, na=False)] if "ORDER_TYPE" in df.columns else pd.DataFrame()

    call_premium = float(call_df["PREMIUM"].sum()) if not call_df.empty and "PREMIUM" in call_df.columns else 0.0
    put_premium = float(put_df["PREMIUM"].sum()) if not put_df.empty and "PREMIUM" in put_df.columns else 0.0

    call_pct = (call_premium / total_premium * 100.0) if total_premium > 0 else 0.0
    put_pct = (put_premium / total_premium * 100.0) if total_premium > 0 else 0.0

    # Net Score & Market Directional Bias
    net_score_val = None
    if "NET_SCORE" in df.columns and df["NET_SCORE"].dropna().any():
        net_score_val = float(df["NET_SCORE"].dropna().mean())

    if net_score_val is not None:
        net_score_str = f"{net_score_val:+.2f}"
    else:
        net_score_str = "N/A"

    if call_pct >= 55.0 or (net_score_val is not None and net_score_val > 0.3):
        bias = "BULLISH"
    elif put_pct >= 55.0 or (net_score_val is not None and net_score_val < -0.3):
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    # Top 5 Bullish Tickers by Call Volume ($)
    if not call_df.empty and "SYMBOL" in call_df.columns:
        top_calls = call_df.groupby("SYMBOL")["PREMIUM"].sum().sort_values(ascending=False).head(5)
        bullish_lines = [f"  • {sym}: {_format_dollar_amount(val)}" for sym, val in top_calls.items()]
    else:
        bullish_lines = ["  • None"]

    # Top 5 Bearish Tickers by Put Volume ($)
    if not put_df.empty and "SYMBOL" in put_df.columns:
        top_puts = put_df.groupby("SYMBOL")["PREMIUM"].sum().sort_values(ascending=False).head(5)
        bearish_lines = [f"  • {sym}: {_format_dollar_amount(val)}" for sym, val in top_puts.items()]
    else:
        bearish_lines = ["  • None"]

    # Top 5 Largest Individual Whale Sweep Prints
    sorted_df = df.sort_values(by="PREMIUM", ascending=False) if "PREMIUM" in df.columns else df
    top_prints = sorted_df.head(5)

    print_lines = []
    for _, row in top_prints.iterrows():
        t_date = str(row.get("TRADE_DATE", ""))[:10]
        sym = str(row.get("SYMBOL", "N/A")).upper()
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
        print_lines.append(f"  • {sym} ({t_date}): {prem} {o_type} | Strike: {strike_fmt}{otm_str} | Exp: {exp} | OI: {oi_fmt}{unusual_flag}")

    prints_block = "\n".join(print_lines) if print_lines else "  • None"

    header = f"[MARKET-WIDE UNUSUAL OPTIONS FLOW: {display_date}]"
    vol_line = f"• Total Flow Volume: {_format_dollar_amount(total_premium)} (Call Flow: {_format_dollar_amount(call_premium)} [{call_pct:.1f}%] | Put Flow: {_format_dollar_amount(put_premium)} [{put_pct:.1f}%])"
    sentiment_line = f"• Market Sentiment Score: {net_score_str} | Net Directional Bias: {bias}"
    top_bull_hdr = "• Top Bullish Tickers (Call Volume):"
    top_bear_hdr = "• Top Bearish Tickers (Put Volume):"
    top_whale_hdr = "• Top Whale Sweeps & Block Prints:"

    return (
        f"{header}\n"
        f"{vol_line}\n"
        f"{sentiment_line}\n"
        f"{top_bull_hdr}\n"
        f"{chr(10).join(bullish_lines)}\n"
        f"{top_bear_hdr}\n"
        f"{chr(10).join(bearish_lines)}\n"
        f"{top_whale_hdr}\n"
        f"{prints_block}"
    )


def format_pure_flow_table(df: Optional[pd.DataFrame], date_label: str = "") -> str:
    """Formats raw flow records into a 100% complete institutional Bloomberg Markdown Table.
    Zero unsolicited analysis or commentary."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        lbl = f" for '{date_label}'" if date_label else ""
        return f"No unusual institutional options flow recorded{lbl}."

    # Sort descending by Premium by default
    if "PREMIUM" in df.columns:
        df_sorted = df.sort_values(by=["PREMIUM", "TRADE_DATE"], ascending=[False, False])
    else:
        df_sorted = df

    headers = ["Symbol", "Order Action", "Strike", "OTM %", "Expiration", "Open Interest", "Premium"]
    rows = []

    for _, row in df_sorted.iterrows():
        sym = str(row.get("SYMBOL", "")).upper()
        
        # Action formatting (e.g. BUY CALL, SELL PUT, BUY PUT, SELL CALL)
        raw_order = str(row.get("ORDER_TYPE", "")).replace("_", " ").upper()
        if "BUY CALL" in raw_order or raw_order == "CALL":
            action_str = "BUY CALL"
        elif "SELL PUT" in raw_order:
            action_str = "SELL PUT"
        elif "BUY PUT" in raw_order or raw_order == "PUT":
            action_str = "BUY PUT"
        elif "SELL CALL" in raw_order:
            action_str = "SELL CALL"
        else:
            action_str = raw_order

        # Strike
        strike_val = row.get("STRIKE_PRICE", "N/A")
        try:
            strike_str = f"${float(strike_val):.2f}"
        except Exception:
            strike_str = f"${strike_val}"

        # OTM %
        otm_val = row.get("STRIKE_OTM_PCT")
        if pd.notna(otm_val) and isinstance(otm_val, (int, float)):
            otm_str = f"{float(otm_val):+.1f}%"
        else:
            otm_str = "+0.0%"

        # Expiration Date
        exp_str = str(row.get("EXPIRATION_DATE", ""))[:10]

        # Open Interest
        oi_val = row.get("OPEN_INTEREST", 0)
        try:
            oi_num = int(oi_val)
            oi_str = f"{oi_num:,}"
        except Exception:
            oi_str = str(oi_val)
        
        if row.get("IS_UNUSUAL_OI") in (1, True, "1"):
            oi_str += " ⚠️"

        # Premium
        prem_val = row.get("PREMIUM", 0.0)
        prem_str = _format_dollar_amount(prem_val)

        rows.append(f"| **{sym}** | {action_str} | {strike_str} | {otm_str} | {exp_str} | {oi_str} | {prem_str} |")

    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join([":---"] * len(headers)) + " |"
    table_block = "\n".join([header_line, separator_line] + rows)

    return table_block


@register_tool(
    name="get_unusual_flow",
    description=(
        "Retrieves 100% complete institutional unusual options flow prints as a pure-data Bloomberg table. "
        "Accepts an optional date parameter (e.g. '2026-08-21', 'Friday', 'yesterday', '2026-08-17 to 2026-08-21', 'latest'). "
        "If omitted, automatically defaults to the latest recorded market session. "
        "Returns raw tabular data only."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Optional market session date, range, or keyword (e.g. '2026-08-21', 'Friday', 'yesterday', '2026-08-17 to 2026-08-21', 'latest'). Defaults to latest session if omitted."
            }
        }
    }
)
def get_unusual_flow(
    date: Optional[str] = None,
    force_refresh: bool = False,
    **kwargs: Any
) -> str:
    """
    Queries institutional unusual options flow from PostgreSQL/Oracle DB via common_lib.
    Supports single date, date ranges, weekdays, and latest session default.
    100% complete prints with zero unsolicited analysis in pure Bloomberg Markdown table.
    """
    t0 = time.perf_counter()

    raw_input = date if date is not None else kwargs.get("trade_date") or kwargs.get("ticker") or kwargs.get("date_input")
    clean_date_str = str(raw_input).strip() if raw_input is not None else ""
    clean_date_str = re.sub(r"^(?:/flow\s*)", "", clean_date_str, flags=re.IGNORECASE).strip()

    if clean_date_str.lower() in ("", "none", "latest"):
        target_date_param = None
        cache_label = "LATEST"
    else:
        target_date_param = clean_date_str
        cache_label = clean_date_str.upper()

    cache_key = f"FLOW_DATE_{cache_label}"
    now = time.time()
    if not force_refresh and cache_key in _FLOW_MEMORY_CACHE:
        ts, cached_table = _FLOW_MEMORY_CACHE[cache_key]
        if now - ts < CACHE_TTL_SECONDS:
            record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="HIT", retry_count=0)
            _LAST_EXECUTED_FLOW_RESULT["latest"] = (time.time(), cached_table)
            return cached_table

    df_flow = pd.DataFrame()
    try:
        from common_lib.config.main_config import load_config
        config = load_config()
        db_type = getattr(config, "db_type", "postgres").lower()

        if db_type == "postgres":
            from common_lib.connectors.postgres import get_unusual_flow as pg_get_flow
            df_flow = pg_get_flow(
                config=config,
                date_input=target_date_param,
                limit=None  # 100% of ALL entries
            )
        else:
            from common_lib.connectors.oracle import get_unusual_flow as oracle_get_flow
            df_flow = oracle_get_flow(
                config=config,
                trade_date=target_date_param or "latest",
                limit=None
            )
    except Exception as ex:
        logger.warning(f"Failed to query DB for unusual options flow ({clean_date_str}): {ex}")
        df_flow = pd.DataFrame()

    table_result = format_pure_flow_table(df_flow, clean_date_str)
    _store_flow_cache(cache_key, table_result)
    record_tool_metric(
        latency_ms=(time.perf_counter() - t0) * 1000.0,
        cache_status="MISS",
        retry_count=0
    )
    _LAST_EXECUTED_FLOW_RESULT["latest"] = (time.time(), table_result)
    return table_result
