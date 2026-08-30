import logging
import subprocess
import os
import sys
from datetime import datetime, date, timedelta, time
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from common_lib.config.main_config import load_config
from common_lib.connectors import postgres
from app.core.auth import get_current_user

logger = logging.getLogger("quant.gateway.flow_status")

router = APIRouter(tags=["Flow Ingestion Status"])


class FlowStatusResponse(BaseModel):
    status: str
    is_fresh: bool
    latest_trade_date: Optional[str]
    last_market_day: str
    total_records: int
    last_session_records: int
    message: str


class FlowSyncResponse(BaseModel):
    status: str
    message: str
    rows_upserted: Optional[int] = None


def get_last_market_day(ref_dt: Optional[datetime] = None) -> date:
    """
    Determines the expected market trading day based on day of week and 6:30 AM cutoff.
    - If Saturday (5) or Sunday (6): Last market day is Friday.
    - If Monday (0): Last market day is Friday.
    - If Tuesday (1) to Friday (4):
      - Before 6:30 AM: 2 calendar days ago (or Friday if Tuesday).
      - After 6:30 AM: Yesterday (1 calendar day ago).
    """
    now = ref_dt or datetime.now()
    weekday = now.weekday()  # 0=Monday, ..., 6=Sunday
    cutoff_time = time(6, 30)
    is_after_cutoff = now.time() >= cutoff_time

    if weekday == 5:  # Saturday
        return (now - timedelta(days=1)).date()  # Friday
    elif weekday == 6:  # Sunday
        return (now - timedelta(days=2)).date()  # Friday
    elif weekday == 0:  # Monday
        return (now - timedelta(days=3)).date()  # Friday
    elif weekday == 1:  # Tuesday
        if is_after_cutoff:
            return (now - timedelta(days=1)).date()  # Monday
        else:
            return (now - timedelta(days=4)).date()  # Friday
    else:  # Wednesday, Thursday, Friday (2, 3, 4)
        if is_after_cutoff:
            return (now - timedelta(days=1)).date()  # Yesterday
        else:
            return (now - timedelta(days=2)).date()  # 2 days ago


def pd_not_na(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    return s not in ("none", "nan", "nat", "null", "")


@router.get("/status", response_model=FlowStatusResponse)
async def get_flow_status():
    """
    Returns the freshness status of the institutional options flow dataset in PostgreSQL.
    """
    expected_market_day = get_last_market_day()
    expected_str = expected_market_day.strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    try:
        config = load_config()
        sql_summary = """
        SELECT 
            MAX(trade_date) AS max_date,
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE trade_date = :expected_day) AS expected_day_count
        FROM unusual_option_flow_te
        WHERE trade_date <= :tomorrow_str;
        """
        df = postgres.sql(config, sql_summary, params={"expected_day": expected_str, "tomorrow_str": tomorrow_str})
        
        if df.empty:
            return FlowStatusResponse(
                status="stale",
                is_fresh=False,
                latest_trade_date=None,
                last_market_day=expected_str,
                total_records=0,
                last_session_records=0,
                message="No flow records found in database."
            )
            
        row = {str(k).lower(): v for k, v in df.iloc[0].items()}
        max_date_val = str(row.get("max_date")) if pd_not_na(row.get("max_date")) else None
        total_count = int(row.get("total_count", 0))
        expected_day_count = int(row.get("expected_day_count", 0))

        # Freshness Check: Must have at least 1 trade date matching or exceeding expected market day
        is_fresh = False
        if max_date_val:
            try:
                latest_d = datetime.strptime(max_date_val.split()[0], "%Y-%m-%d").date()
                is_fresh = (latest_d >= expected_market_day)
            except Exception:
                is_fresh = (max_date_val >= expected_str)

        status_str = "synced" if is_fresh else "stale"
        message_str = (
            f"Flow data is up to date (Session: {max_date_val})."
            if is_fresh
            else f"Flow data is missing latest session (Expected: {expected_str}, Latest: {max_date_val or 'None'})."
        )

        return FlowStatusResponse(
            status=status_str,
            is_fresh=is_fresh,
            latest_trade_date=max_date_val,
            last_market_day=expected_str,
            total_records=total_count,
            last_session_records=expected_day_count,
            message=message_str
        )

    except Exception as ex:
        logger.error(f"Error querying flow status: {ex}", exc_info=True)
        return FlowStatusResponse(
            status="error",
            is_fresh=False,
            latest_trade_date=None,
            last_market_day=expected_str,
            total_records=0,
            last_session_records=0,
            message=f"Database query error: {str(ex)}"
        )


@router.post("/sync", response_model=FlowSyncResponse)
async def trigger_flow_sync(current_user: str = Depends(get_current_user)):
    """
    Manually triggers the daily incremental options flow ingestion pipeline on the host or in-process.
    Auth protected (requires valid session token).
    """
    logger.info(f"User '{current_user}' triggered manual Options Flow sync.")
    
    try:
        from common_lib.flow.runner import run_daily_incremental
        config = load_config()
        rows = run_daily_incremental(config)
        return FlowSyncResponse(
            status="ok",
            message=f"Options Flow sync completed successfully. Ingested {rows} records.",
            rows_upserted=rows
        )
    except Exception as ex:
        logger.error(f"In-process pipeline sync failed: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline execution failed: {str(ex)}"
        )
