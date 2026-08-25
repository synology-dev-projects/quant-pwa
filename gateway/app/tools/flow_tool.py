import re
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


@register_tool(
    name="get_unusual_flow",
    description=(
        "Retrieves institutional unusual options flow, smart money blocks, aggressive sweeps, "
        "and volume-to-open-interest anomalies for single/multiple tickers or market-wide for a specific date. "
        "Supports ticker symbols (e.g. 'NVDA', 'SPY', 'AAPL,MSFT') or date queries (e.g. '2026-08-21', 'yesterday', 'latest', 'MARKET')."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock or ETF ticker symbol (e.g. 'NVDA', 'SPY', 'AAPL,MSFT') OR a date/market string ('2026-08-21', 'yesterday', 'latest', 'MARKET')."
            },
            "trade_date": {
                "type": "string",
                "description": "Optional specific trade date (YYYY-MM-DD, 'yesterday', 'latest') to filter options flow."
            },
            "lookback_days": {
                "type": "integer",
                "description": "Number of days to look back for unusual flow prints when no specific trade_date is given (default: 30)"
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
    ticker: Optional[str] = "SPY",
    trade_date: Optional[str] = None,
    lookback_days: int = 30,
    min_premium: float = 0.0,
    force_refresh: bool = False
) -> str:
    """
    Queries institutional unusual options flow from PostgreSQL/Oracle DB via common_lib.
    Supports smart single-day date / market queries and multi-ticker lookback queries.
    Guarded by SWR in-memory cache (300s TTL), live scrape fallback, and fault isolation.
    """
    t0 = time.perf_counter()
    raw_str = str(ticker or "").strip()
    raw_str = re.sub(r"^(?:/(?:flow|gex|strikes)\s+)", "", raw_str, flags=re.IGNORECASE).strip()

    # Smart Classifier: Detect if ticker input represents a date or market-wide query
    is_market_date = False
    target_market_date: Optional[str] = None

    if trade_date is not None and str(trade_date).strip() != "":
        target_market_date = str(trade_date).strip()

    clean_raw_upper = raw_str.upper().replace("$", "")
    if clean_raw_upper in MARKET_DATE_KEYWORDS or any(p.match(raw_str) for p in DATE_PATTERNS):
        is_market_date = True
        if target_market_date is None:
            target_market_date = clean_raw_upper if clean_raw_upper in MARKET_DATE_KEYWORDS else raw_str
    elif target_market_date is not None and clean_raw_upper in ("SPY", "MARKET", "ALL", ""):
        # User passed a specific trade date and default/broad ticker: treat as market-wide date query
        is_market_date = True

    if is_market_date:
        market_date_key = str(target_market_date or "latest").upper()
        cache_key = f"MARKET_DATE_{market_date_key}_{min_premium}"
        now = time.time()
        if not force_refresh and cache_key in _FLOW_MEMORY_CACHE:
            ts, cached_summary = _FLOW_MEMORY_CACHE[cache_key]
            if now - ts < CACHE_TTL_SECONDS:
                record_tool_metric(latency_ms=(time.perf_counter() - t0) * 1000.0, cache_status="HIT", retry_count=0)
                return cached_summary

        df_market = pd.DataFrame()
        try:
            from common_lib.config.main_config import load_config
            config = load_config()
            db_type = getattr(config, "db_type", "postgres").lower()

            if db_type == "postgres":
                from common_lib.connectors.postgres import get_unusual_flow as pg_get_flow
                df_market = pg_get_flow(
                    config=config,
                    symbols=None,
                    trade_date=target_market_date,
                    min_premium=min_premium,
                    limit=100
                )
            else:
                from common_lib.connectors.oracle import get_unusual_flow as oracle_get_flow
                df_market = oracle_get_flow(
                    config=config,
                    symbols=None,
                    trade_date=target_market_date,
                    min_premium=min_premium,
                    limit=100
                )
        except Exception as ex:
            logger.warning(f"Failed to query DB for market-wide flow ({target_market_date}): {ex}")
            df_market = pd.DataFrame()

        summary = format_market_wide_flow_summary(df_market, str(target_market_date or "latest"))
        _store_flow_cache(cache_key, summary)
        record_tool_metric(
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            cache_status="MISS",
            retry_count=0
        )
        return summary

    # Otherwise, ticker-based query
    raw_parts = [t.strip() for t in raw_str.split(",") if t.strip()]
    raw_tickers = []
    for part in raw_parts:
        cleaned_part = re.sub(r"^(?:/(?:flow|gex|strikes)\s+)", "", part, flags=re.IGNORECASE).strip().upper().replace("$", "")
        if cleaned_part:
            raw_tickers.append(cleaned_part)

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
        cache_key = f"{sym}:{trade_date}:{lookback_days}:{min_premium}" if trade_date else f"{sym}:{lookback_days}:{min_premium}"
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

            db_kwargs: Dict[str, Any] = {
                "config": config,
                "symbols": missing_tickers,
                "lookback_days": lookback_days,
                "min_premium": min_premium,
            }
            if trade_date is not None:
                db_kwargs["trade_date"] = trade_date

            if db_type == "postgres":
                from common_lib.connectors.postgres import get_unusual_flow as pg_get_flow
                df_all = pg_get_flow(**db_kwargs)
            else:
                from common_lib.connectors.oracle import get_unusual_flow as oracle_get_flow
                df_all = oracle_get_flow(**db_kwargs)
        except Exception as ex:
            logger.warning(f"Failed to query DB for batch unusual flow ({missing_tickers}): {ex}")
            df_all = pd.DataFrame()

        for sym in missing_tickers:
            cache_key = f"{sym}:{trade_date}:{lookback_days}:{min_premium}" if trade_date else f"{sym}:{lookback_days}:{min_premium}"
            if not df_all.empty and "SYMBOL" in df_all.columns:
                df_sym = df_all[df_all["SYMBOL"].str.upper() == sym]
            else:
                df_sym = pd.DataFrame()

            if df_sym.empty and trade_date is None:
                # In-process live scrape fallback for specific ticker if lookback mode
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
