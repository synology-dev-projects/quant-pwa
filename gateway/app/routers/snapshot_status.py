import logging
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from common_lib.config.main_config import load_config
from common_lib.connectors import postgres
from app.core.auth import get_current_user

logger = logging.getLogger("quant.gateway.snapshot_status")

router = APIRouter(tags=["GEX/DEX Snapshot Ingestion Status"])


class SnapshotStatusResponse(BaseModel):
    status: str
    is_fresh: bool
    latest_snapshot_date: Optional[str] = None
    latest_date: Optional[str] = None
    expected_date: str
    is_today_market_day: bool
    total_records: int
    latest_snapshot_records: int
    message: str


class SnapshotSyncResponse(BaseModel):
    status: str
    message: str
    rows_upserted: Optional[int] = None
    snapshot_date: Optional[str] = None


def get_market_calendar_context(ref_dt: Optional[datetime] = None) -> tuple[bool, date, date]:
    """
    Evaluates market schedule based on US/Eastern time:
    Returns (is_today_market_day, today_date, last_market_day).
    Accounting for weekends and NYSE official market holidays.
    """
    try:
        eastern = ZoneInfo("America/New_York")
        now = datetime.now(eastern) if ref_dt is None else (
            ref_dt.replace(tzinfo=eastern) if ref_dt.tzinfo is None else ref_dt.astimezone(eastern)
        )
    except Exception:
        now = datetime.now()

    holidays = set()
    try:
        from pandas.tseries.holiday import USFederalHolidayCalendar
        cal = USFederalHolidayCalendar()
        start_search = (now - timedelta(days=30)).date()
        end_search = (now + timedelta(days=5)).date()
        holidays = set(d.date() for d in cal.holidays(start=start_search, end=end_search))
    except Exception as ex:
        logger.warning(f"Could not load US holiday calendar: {ex}")

    today_date = now.date()
    is_today_market_day = (today_date.weekday() < 5 and today_date not in holidays)

    # Calculate last market day before today
    candidate = today_date - timedelta(days=1)
    while candidate.weekday() >= 5 or candidate in holidays:
        candidate -= timedelta(days=1)
    last_market_day = candidate

    return is_today_market_day, today_date, last_market_day


def pd_not_na(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    return s not in ("none", "nan", "nat", "null", "")


@router.get("/status", response_model=SnapshotStatusResponse)
async def get_snapshot_status():
    """
    Returns the freshness status of the GEX/DEX Snapshot fact table in PostgreSQL.
    Rule: In order to be synced, the snapshot date must equal today's date (if a market day)
    OR the last market day.
    """
    is_today_market_day, today_date, last_market_day = get_market_calendar_context()
    today_str = today_date.strftime("%Y-%m-%d")
    last_market_day_str = last_market_day.strftime("%Y-%m-%d")
    expected_str = today_str if is_today_market_day else last_market_day_str

    try:
        config = load_config()
        # Verify table exists
        check_table_sql = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'gexdex_snapshot'
        ) AS tbl_exists;
        """
        tbl_df = postgres.sql(config, check_table_sql)
        if tbl_df.empty or not bool(tbl_df.iloc[0]["tbl_exists"]):
            return SnapshotStatusResponse(
                status="stale",
                is_fresh=False,
                latest_snapshot_date=None,
                latest_date=None,
                expected_date=expected_str,
                is_today_market_day=is_today_market_day,
                total_records=0,
                latest_snapshot_records=0,
                message="Table 'gexdex_snapshot' has not yet been initialized in database."
            )

        sql_summary = """
        SELECT 
            MAX(snapshot_date) AS max_date,
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gexdex_snapshot)) AS latest_day_count
        FROM gexdex_snapshot;
        """
        df = postgres.sql(config, sql_summary)
        if df.empty:
            return SnapshotStatusResponse(
                status="stale",
                is_fresh=False,
                latest_snapshot_date=None,
                latest_date=None,
                expected_date=expected_str,
                is_today_market_day=is_today_market_day,
                total_records=0,
                latest_snapshot_records=0,
                message="No snapshot records found in database."
            )

        row = {str(k).lower(): v for k, v in df.iloc[0].items()}
        max_date_val = str(row.get("max_date")) if pd_not_na(row.get("max_date")) else None
        total_count = int(row.get("total_count", 0))
        latest_day_count = int(row.get("latest_day_count", 0))

        # Freshness Check:
        # If market day: synced if snapshot_date == today OR last_market_day
        # If non-market day: synced if snapshot_date == last_market_day
        valid_dates = {today_date, last_market_day} if is_today_market_day else {last_market_day}
        valid_date_strs = {d.strftime("%Y-%m-%d") for d in valid_dates}

        is_fresh = False
        if max_date_val and latest_day_count > 0:
            clean_date_str = max_date_val.split()[0]
            try:
                latest_d = datetime.strptime(clean_date_str, "%Y-%m-%d").date()
                is_fresh = (latest_d in valid_dates)
            except Exception:
                is_fresh = (clean_date_str in valid_date_strs)

        status_str = "synced" if is_fresh else "stale"
        message_str = (
            f"GEX/DEX Snapshot is up to date (Session: {max_date_val})."
            if is_fresh
            else f"GEX/DEX Snapshot missing latest session (Expected: {expected_str}, Latest: {max_date_val or 'None'})."
        )

        return SnapshotStatusResponse(
            status=status_str,
            is_fresh=is_fresh,
            latest_snapshot_date=max_date_val,
            latest_date=max_date_val,
            expected_date=expected_str,
            is_today_market_day=is_today_market_day,
            total_records=total_count,
            latest_snapshot_records=latest_day_count,
            message=message_str
        )

    except Exception as ex:
        logger.error(f"Error querying snapshot status: {ex}", exc_info=True)
        return SnapshotStatusResponse(
            status="error",
            is_fresh=False,
            latest_snapshot_date=None,
            latest_date=None,
            expected_date=expected_str,
            is_today_market_day=is_today_market_day,
            total_records=0,
            latest_snapshot_records=0,
            message=f"Database query error: {str(ex)}"
        )


@router.post("/sync", response_model=SnapshotSyncResponse)
async def trigger_snapshot_sync(current_user: str = Depends(get_current_user)):
    """
    Manually triggers the downstream GEX/DEX Snapshot pipeline in-process.
    Auth protected (requires valid session token).
    """
    logger.info(f"User '{current_user}' triggered manual GEX/DEX Snapshot sync.")

    try:
        from app.engine.snapshot_pipeline import run_snapshot_pipeline
        config = load_config()
        rows_written, target_date, message = run_snapshot_pipeline(config=config, force_refresh=True)

        return SnapshotSyncResponse(
            status="ok",
            message=message,
            rows_upserted=rows_written,
            snapshot_date=target_date.strftime("%Y-%m-%d")
        )
    except Exception as ex:
        logger.error(f"In-process snapshot pipeline sync failed: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot pipeline execution failed: {str(ex)}"
        )