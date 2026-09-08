import logging
import math
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple, Set
from zoneinfo import ZoneInfo
import sqlalchemy as sa

logger = logging.getLogger("quant.gateway.snapshot_pipeline")
NY_TZ = ZoneInfo("America/New_York")


def sanitize_call_put_ratio(val: Any) -> str:
    """
    Ensures call_put_ratio is a valid value strictly > 0.
    If 0, negative, None, NaN, or non-numeric, labels as 'N/A'.
    """
    if val is None:
        return "N/A"
    try:
        num = float(val)
        if math.isnan(num) or math.isinf(num) or num <= 0.0:
            return "N/A"
        return f"{num:.2f}"
    except (ValueError, TypeError):
        return "N/A"


def get_expected_trade_session() -> date:
    """
    Determines the expected current/latest trade session date in US/Eastern,
    accounting for weekends and official US market holidays (e.g. Labor Day).
    - If today is a weekday, market hours have concluded (after 16:30 ET), and today is not a holiday: returns today.
    - Otherwise: returns the most recent prior weekday that was NOT a market holiday.
    """
    try:
        from pandas.tseries.holiday import USFederalHolidayCalendar
        cal = USFederalHolidayCalendar()
    except ImportError:
        cal = None

    now_ny = datetime.now(NY_TZ)
    close_cutoff = time(16, 30)

    holidays = set()
    if cal:
        try:
            start_search = (now_ny - timedelta(days=30)).date()
            end_search = (now_ny + timedelta(days=5)).date()
            holidays = set(d.date() for d in cal.holidays(start=start_search, end=end_search))
        except Exception as err:
            logger.warning(f"Failed to calculate holiday calendar: {err}")

    candidate = now_ny.date()
    # If today is a trading day and market has closed for the day
    if candidate.weekday() < 5 and candidate not in holidays and now_ny.time() >= close_cutoff:
        return candidate

    # Otherwise step backwards day-by-day to find the most recent valid market session
    candidate -= timedelta(days=1)
    while candidate.weekday() >= 5 or candidate in holidays:
        candidate -= timedelta(days=1)

    return candidate


def check_session_flow_exists(engine: sa.Engine, session_date: date, config: Any = None) -> bool:
    """
    Verifies that unusual_option_flow_te contains data for session_date.
    If 0 records exist, dispatches a Priority 4 alert via NTFY to 'quant_alerts'.
    """
    session_date_str = session_date.strftime("%Y-%m-%d") if isinstance(session_date, (date, datetime)) else str(session_date)
    query = sa.text("""
        SELECT COUNT(*) 
        FROM unusual_option_flow_te 
        WHERE trade_date = :session_date
    """)
    with engine.connect() as conn:
        count = conn.execute(query, {"session_date": session_date_str}).scalar() or 0

    if count == 0:
        logger.warning(f"Zero flow records found in unusual_option_flow_te for trade session {session_date}!")
        _dispatch_missing_flow_alert(session_date, config)
        return False

    logger.info(f"Verified {count} flow records present for trade session {session_date}.")
    return True


def _dispatch_missing_flow_alert(session_date: date, config: Any = None):
    """Sends NTFY Priority 4 warning notification."""
    try:
        if config is None:
            from common_lib.config.main_config import load_config
            config = load_config()

        endpoint = getattr(config, "ntfy_endpoint", None)
        if not endpoint:
            logger.warning("No ntfy_endpoint configured in MainConfig. Alert skipped.")
            return

        from common_lib.connectors.nfty import send_ntfy_notification
        send_ntfy_notification(
            endpoint=endpoint,
            topic="quant_alerts",
            title=f"Missing Flow Data: Session {session_date}",
            message=f"No unusual options flow records were detected in unusual_option_flow_te for trade session {session_date}. Downstream gexdex_snapshot pipeline halted.",
            priority=4,
            tags="warning,flow"
        )
        logger.info("Dispatched missing flow data alert to NTFY 'quant_alerts'.")
    except Exception as ex:
        logger.error(f"Failed to dispatch NTFY alert: {ex}")


def get_available_trade_dates(engine: sa.Engine, session_date: date, limit: int = 5) -> List[date]:
    """Retrieves up to `limit` distinct trading dates <= session_date."""
    session_date_str = session_date.strftime("%Y-%m-%d") if isinstance(session_date, (date, datetime)) else str(session_date)
    query = sa.text("""
        SELECT DISTINCT trade_date 
        FROM unusual_option_flow_te 
        WHERE trade_date <= :session_date 
          AND trade_date IS NOT NULL
        ORDER BY trade_date DESC 
        LIMIT :limit
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {"session_date": session_date_str, "limit": limit}).scalars().all()
        result_dates: List[date] = []
        for r in rows:
            if isinstance(r, (date, datetime)):
                result_dates.append(r if isinstance(r, date) else r.date())
            elif isinstance(r, str):
                try:
                    result_dates.append(date.fromisoformat(r))
                except Exception:
                    pass
        return result_dates


def generate_scorecard_watchlist(engine: sa.Engine, session_date: date) -> Dict[str, List[str]]:
    """
    Executes the 4 flow scorecard queries across both 3D (3-day) and 1W (5-day) windows:
      1. Top 5 Bullish Premium (BUY_CALL, SELL_PUT)
      2. Top 5 Bullish Hits (BUY_CALL, SELL_PUT)
      3. Top 5 Bearish Premium (BUY_PUT, SELL_CALL)
      4. Top 5 Bearish Hits (BUY_PUT, SELL_CALL)
    Unions the results, performs DISTINCT on ticker symbol, and tracks which scorecards surfaced each ticker.
    """
    trade_dates = get_available_trade_dates(engine, session_date, limit=5)
    if not trade_dates:
        logger.warning(f"No trade dates found <= {session_date} in unusual_option_flow_te.")
        return {}

    window_3d = trade_dates[:3]
    window_1w = trade_dates[:5]

    logger.info(f"Generating Watchlist using 3D window: {window_3d} and 1W window: {window_1w}")
    watchlist: Dict[str, Set[str]] = {}

    def _query_top_tickers(dates: List[date], order_types: Tuple[str, ...], order_by: str, tag: str):
        if not dates:
            return
        date_strs = [d.strftime("%Y-%m-%d") if isinstance(d, (date, datetime)) else str(d) for d in dates]
        query = sa.text(f"""
            SELECT symbol
            FROM unusual_option_flow_te
            WHERE trade_date = ANY(:dates)
              AND order_type = ANY(:order_types)
              AND strike_price > 0
            GROUP BY symbol
            ORDER BY {order_by}
            LIMIT 5
        """)
        with engine.connect() as conn:
            rows = conn.execute(query, {
                "dates": date_strs,
                "order_types": list(order_types)
            }).scalars().all()
            for sym in rows:
                clean_sym = str(sym).strip().upper()
                if clean_sym:
                    if clean_sym not in watchlist:
                        watchlist[clean_sym] = set()
                    watchlist[clean_sym].add(tag)

    # 1. 3D Window Scorecards
    _query_top_tickers(window_3d, ("BUY_CALL", "SELL_PUT"), "SUM(premium) DESC, COUNT(*) DESC", "3D_BULL_PREM")
    _query_top_tickers(window_3d, ("BUY_CALL", "SELL_PUT"), "COUNT(*) DESC, SUM(premium) DESC", "3D_BULL_HITS")
    _query_top_tickers(window_3d, ("BUY_PUT", "SELL_CALL"), "SUM(premium) DESC, COUNT(*) DESC", "3D_BEAR_PREM")
    _query_top_tickers(window_3d, ("BUY_PUT", "SELL_CALL"), "COUNT(*) DESC, SUM(premium) DESC", "3D_BEAR_HITS")

    # 2. 1W Window Scorecards
    _query_top_tickers(window_1w, ("BUY_CALL", "SELL_PUT"), "SUM(premium) DESC, COUNT(*) DESC", "1W_BULL_PREM")
    _query_top_tickers(window_1w, ("BUY_CALL", "SELL_PUT"), "COUNT(*) DESC, SUM(premium) DESC", "1W_BULL_HITS")
    _query_top_tickers(window_1w, ("BUY_PUT", "SELL_CALL"), "SUM(premium) DESC, COUNT(*) DESC", "1W_BEAR_PREM")
    _query_top_tickers(window_1w, ("BUY_PUT", "SELL_CALL"), "COUNT(*) DESC, SUM(premium) DESC", "1W_BEAR_HITS")

    distinct_result = {sym: sorted(list(tags)) for sym, tags in watchlist.items()}
    logger.info(f"Constructed deduplicated watchlist of {len(distinct_result)} tickers: {sorted(distinct_result.keys())}")
    return distinct_result


def collect_gexdex_for_watchlist(
    watchlist: Dict[str, List[str]],
    snapshot_date: date,
    config: Any = None,
    force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """
    Queries TradingEdge GEX/DEX API via common-lib for all tickers in the watchlist.
    Validates metrics, enforces call_put_ratio validation, and compiles snapshot records.
    """
    if not watchlist:
        logger.warning("Empty watchlist provided to GEX/DEX collector.")
        return []

    if config is None:
        from common_lib.config.main_config import load_config
        config = load_config()

    from common_lib.connectors.tradingedge.dexgex import (
        get_authenticated_session,
        extract_raw_data
    )

    session = get_authenticated_session(config, force_refresh=force_refresh)
    if not session:
        logger.error("Failed to authenticate with TradingEdge login gate.")
        raise RuntimeError("TradingEdge session authentication failed.")

    records: List[Dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc)

    logger.info(f"Beginning GEX/DEX collection for {len(watchlist)} watchlist tickers...")

    for ticker, scorecards in sorted(watchlist.items()):
        try:
            logger.info(f"Fetching GEX/DEX data for {ticker}...")
            raw_data = extract_raw_data(config, session, ticker, max_dte=50, strike_range=25)

            if raw_data and isinstance(raw_data, dict):
                spot_price = float(raw_data.get("spot_price") or raw_data.get("spotPrice") or 0.0)
                call_put_ratio = sanitize_call_put_ratio(
                    raw_data.get("call_put_ratio") or raw_data.get("callPutRatio")
                )
                call_wall = float(raw_data.get("call_wall") or 0.0)
                put_wall = float(raw_data.get("put_wall") or 0.0)
                zero_flip = float(raw_data.get("zero_gex_level") or raw_data.get("zero_gamma_flip") or spot_price)
                net_gex = float(raw_data.get("net_gex") or 0.0)
                net_dex = float(raw_data.get("net_dex") or 0.0)
                gamma_regime = str(raw_data.get("gamma_regime") or "Neutral")

                strikes = raw_data.get("strikes", [])
                total_call_gex = sum(float(s.get("call_gex", 0.0) or 0.0) for s in strikes) if strikes else None
                total_put_gex = sum(float(s.get("put_gex", 0.0) or 0.0) for s in strikes) if strikes else None
                total_call_dex = sum(float(s.get("call_dex", 0.0) or 0.0) for s in strikes) if strikes else None
                total_put_dex = sum(float(s.get("put_dex", 0.0) or 0.0) for s in strikes) if strikes else None

                records.append({
                    "snapshot_date": snapshot_date,
                    "snapshot_time": now_utc,
                    "ticker": ticker,
                    "spot_price": spot_price if spot_price > 0 else None,
                    "call_put_ratio": call_put_ratio,
                    "call_wall": call_wall if call_wall > 0 else None,
                    "put_wall": put_wall if put_wall > 0 else None,
                    "zero_flip": zero_flip if zero_flip > 0 else None,
                    "net_gex": net_gex,
                    "net_dex": net_dex,
                    "gamma_regime": gamma_regime,
                    "total_call_gex": total_call_gex,
                    "total_put_gex": total_put_gex,
                    "total_call_dex": total_call_dex,
                    "total_put_dex": total_put_dex,
                    "source_scorecards": scorecards
                })
                logger.info(f"Successfully processed {ticker}: Spot=${spot_price:.2f}, C/P={call_put_ratio}")
            else:
                logger.warning(f"No GEX/DEX data returned from TradingEdge for {ticker}.")
                records.append({
                    "snapshot_date": snapshot_date,
                    "snapshot_time": now_utc,
                    "ticker": ticker,
                    "spot_price": None,
                    "call_put_ratio": "N/A",
                    "call_wall": None,
                    "put_wall": None,
                    "zero_flip": None,
                    "net_gex": None,
                    "net_dex": None,
                    "gamma_regime": "Data Unavailable",
                    "total_call_gex": None,
                    "total_put_gex": None,
                    "total_call_dex": None,
                    "total_put_dex": None,
                    "source_scorecards": scorecards
                })
        except Exception as err:
            logger.error(f"Error extracting GEX/DEX for {ticker}: {err}")
            records.append({
                "snapshot_date": snapshot_date,
                "snapshot_time": now_utc,
                "ticker": ticker,
                "spot_price": None,
                "call_put_ratio": "N/A",
                "call_wall": None,
                "put_wall": None,
                "zero_flip": None,
                "net_gex": None,
                "net_dex": None,
                "gamma_regime": "Error",
                "total_call_gex": None,
                "total_put_gex": None,
                "total_call_dex": None,
                "total_put_dex": None,
                "source_scorecards": scorecards
            })

    return records


def ensure_tables(engine: sa.Engine):
    """Creates the gexdex_snapshot fact table and supporting indexes if not present."""
    ddl = """
    CREATE TABLE IF NOT EXISTS gexdex_snapshot (
        snapshot_date DATE NOT NULL,
        snapshot_time TIMESTAMP WITH TIME ZONE NOT NULL,
        ticker VARCHAR(12) NOT NULL,
        spot_price NUMERIC(14, 4),
        call_put_ratio VARCHAR(20) NOT NULL DEFAULT 'N/A',
        call_wall NUMERIC(14, 4),
        put_wall NUMERIC(14, 4),
        zero_flip NUMERIC(14, 4),
        net_gex NUMERIC(20, 2),
        net_dex NUMERIC(20, 2),
        gamma_regime VARCHAR(50),
        total_call_gex NUMERIC(20, 2),
        total_put_gex NUMERIC(20, 2),
        total_call_dex NUMERIC(20, 2),
        total_put_dex NUMERIC(20, 2),
        source_scorecards JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        CONSTRAINT pk_gexdex_snapshot PRIMARY KEY (snapshot_date, ticker)
    );

    CREATE INDEX IF NOT EXISTS idx_gexdex_snapshot_date ON gexdex_snapshot(snapshot_date DESC);
    CREATE INDEX IF NOT EXISTS idx_gexdex_snapshot_ticker ON gexdex_snapshot(ticker);
    """
    with engine.begin() as conn:
        conn.execute(sa.text(ddl))
    logger.info("Table 'gexdex_snapshot' verified successfully.")


def replace_snapshot(engine: sa.Engine, target_date: date, records: List[Dict[str, Any]]) -> int:
    """Atomically replaces the snapshot for target_date inside a transaction."""
    import json
    ensure_tables(engine)

    delete_sql = sa.text("DELETE FROM gexdex_snapshot WHERE snapshot_date = :target_date")
    insert_sql = sa.text("""
        INSERT INTO gexdex_snapshot (
            snapshot_date, snapshot_time, ticker, spot_price, call_put_ratio,
            call_wall, put_wall, zero_flip, net_gex, net_dex, gamma_regime,
            total_call_gex, total_put_gex, total_call_dex, total_put_dex,
            source_scorecards
        ) VALUES (
            :snapshot_date, :snapshot_time, :ticker, :spot_price, :call_put_ratio,
            :call_wall, :put_wall, :zero_flip, :net_gex, :net_dex, :gamma_regime,
            :total_call_gex, :total_put_gex, :total_call_dex, :total_put_dex,
            :source_scorecards
        )
    """)

    prepared_rows = []
    for r in records:
        row = dict(r)
        if "source_scorecards" in row and isinstance(row["source_scorecards"], (list, set, tuple)):
            row["source_scorecards"] = json.dumps(list(row["source_scorecards"]))
        prepared_rows.append(row)

    with engine.begin() as conn:
        del_result = conn.execute(delete_sql, {"target_date": target_date})
        logger.info(f"Deleted {del_result.rowcount} previous rows for snapshot date {target_date}.")

        if prepared_rows:
            conn.execute(insert_sql, prepared_rows)
            logger.info(f"Successfully inserted {len(prepared_rows)} snapshot rows for {target_date}.")

    return len(prepared_rows)


def run_snapshot_pipeline(
    target_date: Optional[date] = None,
    force_refresh: bool = False,
    config: Any = None
) -> Tuple[int, date, str]:
    """
    Executes the complete GEX/DEX snapshot pipeline in-process.
    Returns (rows_upserted, target_date, status_message).
    """
    if config is None:
        from common_lib.config.main_config import load_config
        config = load_config()

    from common_lib.connectors.postgres import get_postgres_engine
    engine = get_postgres_engine(config)

    if target_date is None:
        target_date = get_expected_trade_session()

    logger.info(f"Executing GEX/DEX Snapshot Pipeline for target date: {target_date}")

    # 1. Flow presence verification
    has_flow = check_session_flow_exists(engine, target_date, config=config)
    if not has_flow:
        msg = f"No flow records detected in unusual_option_flow_te for trade session {target_date}."
        logger.warning(msg)
        return 0, target_date, msg

    # 2. Watchlist generation
    watchlist = generate_scorecard_watchlist(engine, target_date)
    if not watchlist:
        msg = f"Watchlist generation produced 0 tickers for {target_date}."
        logger.warning(msg)
        return 0, target_date, msg

    # 3. GEX/DEX collection from TradingEdge
    records = collect_gexdex_for_watchlist(
        watchlist=watchlist,
        snapshot_date=target_date,
        config=config,
        force_refresh=force_refresh
    )

    # 4. Atomic Fact Table update
    rows_written = replace_snapshot(engine, target_date, records)
    msg = f"Successfully committed {rows_written} snapshot rows for session {target_date}."
    logger.info(msg)
    return rows_written, target_date, msg