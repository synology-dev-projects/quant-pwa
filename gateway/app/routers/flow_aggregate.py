import logging
from typing import Dict, Any, List, Optional
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query, Depends
import sqlalchemy as sa
import pandas as pd

from app.core.auth import get_current_user
from app.routers.flow_status import get_last_market_day

logger = logging.getLogger("quant.gateway.flow_aggregate")

router = APIRouter(prefix="/api/flow", tags=["Flow Ingestion Status"])


def _get_engine():
    from common_lib.config.main_config import load_config
    from common_lib.connectors.postgres import get_postgres_engine
    config = load_config()
    return get_postgres_engine(config)


def _format_currency(val: Optional[float]) -> str:
    if val is None:
        return "$0"
    abs_val = abs(val)
    if abs_val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.2f}B"
    elif abs_val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    elif abs_val >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:,.0f}"


def _fetch_window_aggregates(conn: sa.Connection, dates: List[str]) -> Dict[str, Any]:
    if not dates:
        return {
            "market_dates": [],
            "top_premium_bullish": [],
            "top_hits_bullish": [],
            "top_hits_bearish": []
        }

    # 1. Top 5 Bullish by Premium Spent
    q_prem = sa.text("""
        SELECT 
            symbol,
            COALESCE(SUM(premium), 0) AS total_premium,
            COUNT(*) AS contract_count,
            COUNT(DISTINCT trade_date) AS active_days
        FROM unusual_option_flow_te
        WHERE trade_date = ANY(:dates)
          AND order_type IN ('BUY_CALL', 'SELL_PUT')
          AND strike_price > 0
        GROUP BY symbol
        ORDER BY total_premium DESC, contract_count DESC
        LIMIT 5
    """)
    rows_prem = conn.execute(q_prem, {"dates": dates}).mappings().all()
    top_premium_bullish = []
    for idx, r in enumerate(rows_prem, start=1):
        prem = float(r["total_premium"])
        top_premium_bullish.append({
            "rank": idx,
            "symbol": str(r["symbol"]).upper(),
            "total_premium": prem,
            "formatted_premium": _format_currency(prem),
            "contract_count": int(r["contract_count"]),
            "active_days": int(r["active_days"])
        })

    # 2. Top 5 Bullish by Number of Hits / Contracts
    q_bull_hits = sa.text("""
        SELECT 
            symbol,
            COUNT(*) AS contract_count,
            COALESCE(SUM(premium), 0) AS total_premium,
            COUNT(DISTINCT trade_date) AS active_days
        FROM unusual_option_flow_te
        WHERE trade_date = ANY(:dates)
          AND order_type IN ('BUY_CALL', 'SELL_PUT')
          AND strike_price > 0
        GROUP BY symbol
        ORDER BY contract_count DESC, total_premium DESC
        LIMIT 5
    """)
    rows_bull = conn.execute(q_bull_hits, {"dates": dates}).mappings().all()
    top_hits_bullish = []
    for idx, r in enumerate(rows_bull, start=1):
        prem = float(r["total_premium"])
        top_hits_bullish.append({
            "rank": idx,
            "symbol": str(r["symbol"]).upper(),
            "contract_count": int(r["contract_count"]),
            "total_premium": prem,
            "formatted_premium": _format_currency(prem),
            "active_days": int(r["active_days"])
        })

    # 3. Top 5 Bearish by Number of Hits / Contracts
    q_bear_hits = sa.text("""
        SELECT 
            symbol,
            COUNT(*) AS contract_count,
            COALESCE(SUM(premium), 0) AS total_premium,
            COUNT(DISTINCT trade_date) AS active_days
        FROM unusual_option_flow_te
        WHERE trade_date = ANY(:dates)
          AND order_type IN ('BUY_PUT', 'SELL_CALL')
          AND strike_price > 0
        GROUP BY symbol
        ORDER BY contract_count DESC, total_premium DESC
        LIMIT 5
    """)
    rows_bear = conn.execute(q_bear_hits, {"dates": dates}).mappings().all()
    top_hits_bearish = []
    for idx, r in enumerate(rows_bear, start=1):
        prem = float(r["total_premium"])
        top_hits_bearish.append({
            "rank": idx,
            "symbol": str(r["symbol"]).upper(),
            "contract_count": int(r["contract_count"]),
            "total_premium": prem,
            "formatted_premium": _format_currency(prem),
            "active_days": int(r["active_days"])
        })

    return {
        "market_dates": dates,
        "top_premium_bullish": top_premium_bullish,
        "top_hits_bullish": top_hits_bullish,
        "top_hits_bearish": top_hits_bearish
    }


@router.get("/aggregate")
def get_flow_aggregate(
    as_of_date: Optional[str] = Query(None, description="Anchor trade date (YYYY-MM-DD). Defaults to latest completed market session."),
    _: str = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Returns aggregated institutional options flow rankings across two duration windows (3-day and 7-day).
    Includes:
      1. Top 5 Bullish by Premium Spent
      2. Top 5 Bullish by Contract Hits
      3. Top 5 Bearish by Contract Hits
    Zero client derivation required.
    """
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            # 1. Discover distinct trade dates
            if as_of_date:
                anchor_dt = str(pd.to_datetime(as_of_date.strip()).date())
                date_query = sa.text("""
                    SELECT DISTINCT trade_date
                    FROM unusual_option_flow_te
                    WHERE trade_date <= :anchor_date
                      AND strike_price > 0
                    ORDER BY trade_date DESC
                    LIMIT 10
                """)
                distinct_dates = conn.execute(date_query, {"anchor_date": anchor_dt}).scalars().all()
            else:
                last_mkt_day = str(get_last_market_day())
                date_query = sa.text("""
                    SELECT DISTINCT trade_date
                    FROM unusual_option_flow_te
                    WHERE trade_date <= :last_market_day
                      AND strike_price > 0
                    ORDER BY trade_date DESC
                    LIMIT 10
                """)
                distinct_dates = conn.execute(date_query, {"last_market_day": last_mkt_day}).scalars().all()
                if not distinct_dates:
                    fallback_query = sa.text("""
                        SELECT DISTINCT trade_date
                        FROM unusual_option_flow_te
                        WHERE strike_price > 0
                        ORDER BY trade_date DESC
                        LIMIT 10
                    """)
                    distinct_dates = conn.execute(fallback_query).scalars().all()

            distinct_dates_str = [str(d) for d in distinct_dates]
            resolved_as_of = distinct_dates_str[0] if distinct_dates_str else None

            dates_3d = distinct_dates_str[:3]
            dates_7d = distinct_dates_str[:7]

            window_3d = _fetch_window_aggregates(conn, dates_3d)
            window_7d = _fetch_window_aggregates(conn, dates_7d)

            return {
                "as_of_date": resolved_as_of,
                "latest_market_day": str(get_last_market_day()),
                "window_3d": window_3d,
                "window_7d": window_7d,
                "generated_at": datetime.now().isoformat()
            }

    except Exception as ex:
        logger.error(f"Failed to calculate flow aggregates: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error querying flow aggregates: {ex}")
