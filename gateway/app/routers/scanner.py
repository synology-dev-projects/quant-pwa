import logging
from typing import Dict, Any, List, Optional
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
import sqlalchemy as sa
import pandas as pd

from app.core.auth import get_current_user

logger = logging.getLogger("quant.gateway.scanner")

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


def _get_engine():
    from common_lib.config.main_config import load_config
    from common_lib.connectors.postgres import get_postgres_engine
    config = load_config()
    return get_postgres_engine(config)


@router.get("/dates")
def get_available_scan_dates(_: str = Depends(get_current_user)) -> List[str]:
    """Returns a list of all distinct scan dates available in daily_confluence_summary."""
    try:
        engine = _get_engine()
        query = sa.text("SELECT scan_date FROM daily_confluence_summary ORDER BY scan_date DESC")
        with engine.connect() as conn:
            rows = conn.execute(query).scalars().all()
            return [str(r) for r in rows]
    except Exception as ex:
        logger.error(f"Failed to query scanner dates: {ex}")
        return []


@router.get("/latest")
def get_latest_confluence_scan(_: str = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Returns the most recent daily confluence scan results, including pre-computed summary metrics
    and all ticker records sorted by confluence_score DESC, total_flow_premium DESC.
    Zero derivations required by the client.
    """
    try:
        engine = _get_engine()
        # 1. Fetch latest summary record
        sum_query = sa.text("""
            SELECT 
                scan_date,
                session_label,
                total_scanned_count,
                confirmed_bull_count,
                confirmed_bear_count,
                vol_pin_count,
                divergent_count,
                top_whale_ticker,
                top_whale_premium,
                formatted_top_whale_premium,
                market_regime_summary,
                scanned_at
            FROM daily_confluence_summary
            ORDER BY scan_date DESC
            LIMIT 1
        """)
        with engine.connect() as conn:
            summary_row = conn.execute(sum_query).mappings().first()

        if not summary_row:
            return {
                "scan_date": None,
                "summary": None,
                "rows": [],
                "count": 0
            }

        latest_date = summary_row["scan_date"]

        # 2. Fetch all ticker scan rows for this date
        rows_query = sa.text("""
            SELECT 
                scan_date,
                ticker,
                spot_price,
                formatted_spot_price,
                total_flow_premium,
                formatted_flow_premium,
                call_premium,
                put_premium,
                call_premium_pct,
                put_premium_pct,
                flow_bias,
                whale_prints_count,
                top_whale_premium,
                formatted_top_whale_premium,
                top_whale_action,
                net_sentiment_score,
                gamma_regime,
                net_gex,
                formatted_net_gex,
                net_dex,
                formatted_net_dex,
                zero_gamma_flip,
                spot_vs_flip_pct,
                call_wall,
                put_wall,
                wall_spread_range,
                confluence_status,
                confluence_score,
                confluence_rationale
            FROM daily_confluence_scans
            WHERE scan_date = :s_date
            ORDER BY confluence_score DESC, total_flow_premium DESC
        """)

        with engine.connect() as conn:
            scan_rows = conn.execute(rows_query, {"s_date": latest_date}).mappings().all()

        summary_dict = dict(summary_row)
        summary_dict["scan_date"] = str(summary_dict["scan_date"])
        if summary_dict.get("scanned_at"):
            summary_dict["scanned_at"] = str(summary_dict["scanned_at"])
        if summary_dict.get("top_whale_premium") is not None:
            summary_dict["top_whale_premium"] = float(summary_dict["top_whale_premium"])

        clean_rows = []
        for r in scan_rows:
            d = dict(r)
            d["scan_date"] = str(d["scan_date"])
            for float_col in ("spot_price", "total_flow_premium", "call_premium", "put_premium",
                              "call_premium_pct", "put_premium_pct", "top_whale_premium",
                              "net_sentiment_score", "net_gex", "net_dex", "zero_gamma_flip",
                              "spot_vs_flip_pct", "call_wall", "put_wall", "confluence_score"):
                if d.get(float_col) is not None:
                    d[float_col] = float(d[float_col])
            clean_rows.append(d)

        return {
            "scan_date": str(latest_date),
            "summary": summary_dict,
            "rows": clean_rows,
            "count": len(clean_rows)
        }

    except Exception as ex:
        logger.error(f"Failed to fetch latest confluence scan: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error querying confluence scan: {ex}")


@router.get("/by-date")
def get_confluence_scan_by_date(
    date: str = Query(..., description="Target scan date (YYYY-MM-DD)"),
    _: str = Depends(get_current_user)
) -> Dict[str, Any]:
    """Returns pre-computed scan results for a specific historical date."""
    try:
        target_dt = pd.to_datetime(date.strip()).date()
        engine = _get_engine()

        sum_query = sa.text("""
            SELECT 
                scan_date,
                session_label,
                total_scanned_count,
                confirmed_bull_count,
                confirmed_bear_count,
                vol_pin_count,
                divergent_count,
                top_whale_ticker,
                top_whale_premium,
                formatted_top_whale_premium,
                market_regime_summary,
                scanned_at
            FROM daily_confluence_summary
            WHERE scan_date = :s_date
        """)
        with engine.connect() as conn:
            summary_row = conn.execute(sum_query, {"s_date": target_dt}).mappings().first()

        if not summary_row:
            return {
                "scan_date": str(target_dt),
                "summary": None,
                "rows": [],
                "count": 0
            }

        rows_query = sa.text("""
            SELECT 
                scan_date,
                ticker,
                spot_price,
                formatted_spot_price,
                total_flow_premium,
                formatted_flow_premium,
                call_premium,
                put_premium,
                call_premium_pct,
                put_premium_pct,
                flow_bias,
                whale_prints_count,
                top_whale_premium,
                formatted_top_whale_premium,
                top_whale_action,
                net_sentiment_score,
                gamma_regime,
                net_gex,
                formatted_net_gex,
                net_dex,
                formatted_net_dex,
                zero_gamma_flip,
                spot_vs_flip_pct,
                call_wall,
                put_wall,
                wall_spread_range,
                confluence_status,
                confluence_score,
                confluence_rationale
            FROM daily_confluence_scans
            WHERE scan_date = :s_date
            ORDER BY confluence_score DESC, total_flow_premium DESC
        """)

        with engine.connect() as conn:
            scan_rows = conn.execute(rows_query, {"s_date": target_dt}).mappings().all()

        summary_dict = dict(summary_row)
        summary_dict["scan_date"] = str(summary_dict["scan_date"])
        if summary_dict.get("scanned_at"):
            summary_dict["scanned_at"] = str(summary_dict["scanned_at"])
        if summary_dict.get("top_whale_premium") is not None:
            summary_dict["top_whale_premium"] = float(summary_dict["top_whale_premium"])

        clean_rows = []
        for r in scan_rows:
            d = dict(r)
            d["scan_date"] = str(d["scan_date"])
            for float_col in ("spot_price", "total_flow_premium", "call_premium", "put_premium",
                              "call_premium_pct", "put_premium_pct", "top_whale_premium",
                              "net_sentiment_score", "net_gex", "net_dex", "zero_gamma_flip",
                              "spot_vs_flip_pct", "call_wall", "put_wall", "confluence_score"):
                if d.get(float_col) is not None:
                    d[float_col] = float(d[float_col])
            clean_rows.append(d)

        return {
            "scan_date": str(target_dt),
            "summary": summary_dict,
            "rows": clean_rows,
            "count": len(clean_rows)
        }

    except Exception as ex:
        logger.error(f"Failed to query scan for date {date}: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {ex}")
