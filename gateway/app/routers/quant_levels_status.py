import logging
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from common_lib.config.main_config import load_config
from common_lib.connectors import postgres
from app.core.auth import get_current_user

logger = logging.getLogger("quant.gateway.quant_levels_status")

router = APIRouter(tags=["Quant Levels Ingestion Status"])


class QuantLevelStatusResponse(BaseModel):
    status: str
    is_fresh: bool
    latest_record_date: Optional[str] = None
    latest_date: Optional[str] = None
    expected_date: str
    total_records: int
    expected_day_records: int
    message: str


class QuantLevelSyncResponse(BaseModel):
    status: str
    message: str
    rows_upserted: Optional[int] = None


def get_expected_quant_levels_date(ref_dt: Optional[datetime] = None) -> date:
    """
    Determines the expected quant levels date based on US/Eastern time:
    - Weekends (Saturday=5, Sunday=6): returns Friday.
    - Weekday (Monday=0 to Friday=4):
      - If hour < 6 or (hour == 6 and minute < 30) Eastern Time: returns previous market day (Friday if Monday; yesterday if Tue-Fri).
      - If >= 6:30 AM Eastern Time: returns today's date.
    """
    try:
        eastern = ZoneInfo("America/New_York")
        if ref_dt is None:
            now = datetime.now(eastern)
        else:
            if ref_dt.tzinfo is None:
                now = ref_dt.replace(tzinfo=eastern)
            else:
                now = ref_dt.astimezone(eastern)
    except Exception:
        # Fallback timezone offset: UTC-4 (EDT) or system local
        edt_tz = timezone(timedelta(hours=-4))
        if ref_dt is None:
            now = datetime.now(edt_tz)
        else:
            if ref_dt.tzinfo is None:
                now = ref_dt.replace(tzinfo=edt_tz)
            else:
                now = ref_dt.astimezone(edt_tz)

    weekday = now.weekday()  # 0=Monday, ..., 6=Sunday
    cutoff_time = time(6, 30)
    is_after_cutoff = (now.time() >= cutoff_time)

    if weekday == 5:  # Saturday
        return (now - timedelta(days=1)).date()  # Friday
    elif weekday == 6:  # Sunday
        return (now - timedelta(days=2)).date()  # Friday
    elif weekday == 0:  # Monday
        if is_after_cutoff:
            return now.date()  # Monday (Today)
        else:
            return (now - timedelta(days=3)).date()  # Friday
    else:  # Tuesday (1), Wednesday (2), Thursday (3), Friday (4)
        if is_after_cutoff:
            return now.date()  # Today
        else:
            return (now - timedelta(days=1)).date()  # Yesterday


def pd_not_na(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    return s not in ("none", "nan", "nat", "null", "")


@router.get("/status", response_model=QuantLevelStatusResponse)
async def get_quant_levels_status():
    """
    Returns the freshness status of the Quant Levels dataset in PostgreSQL.
    """
    expected_str = datetime.now().strftime("%Y-%m-%d")
    try:
        expected_date = get_expected_quant_levels_date()
        expected_str = expected_date.strftime("%Y-%m-%d")
        config = load_config()
        sql_summary = """
        SELECT 
            MAX(DATE(datetime)) AS max_date,
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE DATE(datetime) = :expected_date) AS expected_day_count
        FROM quant_lvl_data_te;
        """
        df = postgres.sql(config, sql_summary, params={"expected_date": expected_str})

        if df.empty:
            return QuantLevelStatusResponse(
                status="stale",
                is_fresh=False,
                latest_record_date=None,
                latest_date=None,
                expected_date=expected_str,
                total_records=0,
                expected_day_records=0,
                message="No quant level records found in database."
            )

        row = {str(k).lower(): v for k, v in df.iloc[0].items()}
        max_date_val = str(row.get("max_date")) if pd_not_na(row.get("max_date")) else None
        total_count = int(row.get("total_count", 0))
        expected_day_count = int(row.get("expected_day_count", 0))

        # Freshness Check: max_date >= expected_date and expected_day_count > 0
        is_fresh = False
        if max_date_val:
            try:
                latest_d = datetime.strptime(max_date_val.split()[0], "%Y-%m-%d").date()
                is_fresh = (latest_d >= expected_date and expected_day_count > 0)
            except Exception:
                is_fresh = (max_date_val >= expected_str and expected_day_count > 0)

        status_str = "synced" if is_fresh else "stale"
        message_str = (
            f"Quant levels are up to date (Session: {max_date_val})."
            if is_fresh
            else f"Quant levels missing latest session (Expected: {expected_str}, Latest: {max_date_val or 'None'})."
        )

        return QuantLevelStatusResponse(
            status=status_str,
            is_fresh=is_fresh,
            latest_record_date=max_date_val,
            latest_date=max_date_val,
            expected_date=expected_str,
            total_records=total_count,
            expected_day_records=expected_day_count,
            message=message_str
        )

    except Exception as ex:
        logger.error(f"Error querying quant levels status: {ex}", exc_info=True)
        return QuantLevelStatusResponse(
            status="error",
            is_fresh=False,
            latest_record_date=None,
            latest_date=None,
            expected_date=expected_str,
            total_records=0,
            expected_day_records=0,
            message=f"Database query error: {str(ex)}"
        )


@router.post("/sync", response_model=QuantLevelSyncResponse)
async def trigger_quant_levels_sync(current_user: str = Depends(get_current_user)):
    """
    Manually triggers the daily incremental quant levels ingestion pipeline.
    Auth protected (requires valid session token).
    """
    logger.info(f"User '{current_user}' triggered manual Quant Levels sync.")

    try:
        from common_lib.quant_levels.runner import run_daily_incremental
        config = load_config()
        rows = run_daily_incremental(config)
        return QuantLevelSyncResponse(
            status="ok",
            message=f"Quant Levels sync completed successfully. Ingested {rows} records.",
            rows_upserted=rows
        )
    except Exception as ex:
        logger.error(f"In-process quant levels pipeline sync failed: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline execution failed: {str(ex)}"
        )
