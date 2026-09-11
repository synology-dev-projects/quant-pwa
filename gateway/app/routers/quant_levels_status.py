import logging
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo
from typing import Optional, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import pandas as pd

from common_lib.config.main_config import load_config
from common_lib.connectors import postgres
from app.core.auth import get_current_user
from app.core.quote_feed import get_batch_quotes

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


class QuantLevelItem(BaseModel):
    start_price: float
    end_price: Optional[float] = None
    price_display: str
    type: str  # "BUY", "SELL", or "PIVOT"
    comments: Optional[str] = None
    web_link: Optional[str] = None
    distance_pts: float
    distance_pct: float
    relative_position: str  # "ABOVE_SPOT", "BELOW_SPOT", or "AT_SPOT"
    is_immediate_support: bool = False
    is_immediate_resistance: bool = False


class QuantLevelSummary(BaseModel):
    ticker: str
    as_of_date: Optional[str] = None
    spot_price: Optional[float] = None
    immediate_resistance: Optional[float] = None
    immediate_support: Optional[float] = None
    channel_width: Optional[float] = None
    total_levels: int
    buy_levels_count: int
    sell_levels_count: int


class QuantLevelDataResponse(BaseModel):
    status: str
    ticker: str
    as_of_date: Optional[str] = None
    available_dates: List[str] = []
    spot_price: Optional[float] = None
    summary: QuantLevelSummary
    levels: List[QuantLevelItem] = []
    message: Optional[str] = None


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


@router.get("/dates", response_model=List[str])
async def get_quant_levels_dates(ticker: str = "SPX"):
    """
    Returns distinct available historical as-of dates for SPX in descending order.
    The Quant Levels tab is strictly locked to ticker SPX.
    """
    clean_ticker = "SPX"
    try:
        config = load_config()
        query = """
            SELECT DISTINCT datetime::date AS d
            FROM quant_lvl_data_te
            WHERE ticker = :ticker
            ORDER BY d DESC;
        """
        df = postgres.sql(config, query, params={"ticker": clean_ticker})
        if df.empty:
            return []
        dates = [
            str(row["d"]).split()[0]
            for _, row in df.iterrows()
            if pd_not_na(row["d"])
        ]
        return dates
    except Exception as ex:
        logger.warning(f"Error fetching quant level dates for {clean_ticker}: {ex}")
        return []


@router.get("/data", response_model=QuantLevelDataResponse)
async def get_quant_levels_data(
    ticker: str = "SPX",
    as_of_date: Optional[str] = None
):
    """
    Fetches structured quant levels strictly locked to ticker SPX, enriched with live spot prices,
    spot distance deltas, and immediate support/resistance flags.
    """
    clean_ticker = "SPX"

    config = load_config()
    target_date: Optional[date] = None

    # 1. Fetch available dates for SPX
    dates_query = """
        SELECT DISTINCT datetime::date AS d
        FROM quant_lvl_data_te
        WHERE ticker = :ticker
        ORDER BY d DESC;
    """
    try:
        df_dates = postgres.sql(config, dates_query, params={"ticker": clean_ticker})
        available_dates = [
            str(row["d"]).split()[0]
            for _, row in df_dates.iterrows()
            if pd_not_na(row["d"])
        ] if not df_dates.empty else []
    except Exception as ex:
        logger.warning(f"Failed fetching dates for {clean_ticker}: {ex}")
        available_dates = []

    # Resolve target date
    if as_of_date and as_of_date.strip():
        try:
            target_date = datetime.strptime(as_of_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            target_date = None
    elif available_dates:
        try:
            target_date = datetime.strptime(available_dates[0], "%Y-%m-%d").date()
        except ValueError:
            target_date = None

    # 2. Concurrently fetch spot price
    spot_price: Optional[float] = None
    quote_syms = [clean_ticker]
    if clean_ticker == "SPX":
        quote_syms.append("^SPX")
    elif clean_ticker == "NDX":
        quote_syms.append("^NDX")

    try:
        quotes = await get_batch_quotes(quote_syms)
        for sym in quote_syms:
            if sym in quotes and quotes[sym].get("price"):
                spot_price = float(quotes[sym]["price"])
                break
    except Exception as ex:
        logger.warning(f"Failed fetching spot price for {clean_ticker}: {ex}")

    # 3. Query quant levels from postgres
    try:
        df_levels = postgres.get_quant_levels(config, ticker=clean_ticker, as_of_date=target_date)
    except Exception as ex:
        logger.error(f"Error querying quant levels for {clean_ticker}: {ex}")
        df_levels = pd.DataFrame()

    if df_levels.empty:
        summary = QuantLevelSummary(
            ticker=clean_ticker,
            as_of_date=str(target_date) if target_date else None,
            spot_price=spot_price,
            immediate_resistance=None,
            immediate_support=None,
            channel_width=None,
            total_levels=0,
            buy_levels_count=0,
            sell_levels_count=0
        )
        return QuantLevelDataResponse(
            status="empty",
            ticker=clean_ticker,
            as_of_date=str(target_date) if target_date else None,
            available_dates=available_dates,
            spot_price=spot_price,
            summary=summary,
            levels=[],
            message=f"No quant levels found for {clean_ticker} as of {target_date or 'latest'}."
        )

    # Filter to exact target_date if resolved and DATETIME present
    if target_date is not None and "DATETIME" in df_levels.columns:
        df_levels["DATE_ONLY"] = pd.to_datetime(df_levels["DATETIME"]).dt.date
        date_filtered = df_levels[df_levels["DATE_ONLY"] == target_date].copy()
        if not date_filtered.empty:
            df_levels = date_filtered
        else:
            # Fallback to latest available date in DataFrame
            max_d = pd.to_datetime(df_levels["DATETIME"]).dt.date.max()
            df_levels = df_levels[pd.to_datetime(df_levels["DATETIME"]).dt.date == max_d].copy()
            target_date = max_d
    elif "DATETIME" in df_levels.columns:
        max_d = pd.to_datetime(df_levels["DATETIME"]).dt.date.max()
        df_levels = df_levels[pd.to_datetime(df_levels["DATETIME"]).dt.date == max_d].copy()
        target_date = max_d

    # Convert to structured items
    items: List[QuantLevelItem] = []
    buy_count = 0
    sell_count = 0

    df_levels["START_LVL_PRICE"] = pd.to_numeric(df_levels["START_LVL_PRICE"], errors="coerce")
    df_levels = df_levels.dropna(subset=["START_LVL_PRICE"])
    df_levels = df_levels.sort_values(by="START_LVL_PRICE", ascending=False)

    ref_spot = spot_price or (
        float(df_levels["START_LVL_PRICE"].median()) if not df_levels.empty else 0.0
    )

    for _, row in df_levels.iterrows():
        start_p = float(row["START_LVL_PRICE"])
        end_p = float(row["END_LVL_PRICE"]) if pd_not_na(row.get("END_LVL_PRICE")) else None

        raw_ind = str(row.get("BUY_SELL_IND") or "").strip().upper()
        if raw_ind in ("BUY", "LONG"):
            lvl_type = "BUY"
            buy_count += 1
        elif raw_ind in ("SELL", "SHORT"):
            lvl_type = "SELL"
            sell_count += 1
        else:
            lvl_type = "PIVOT"

        comments = str(row.get("COMMENTS") or "").strip() or None
        web_link = str(row.get("WEB_LINK") or "").strip() or None

        mid_p = (start_p + end_p) / 2.0 if end_p is not None else start_p
        dist_pts = round(mid_p - ref_spot, 2)
        dist_pct = round((dist_pts / ref_spot) * 100, 2) if ref_spot > 0 else 0.0

        if abs(dist_pct) <= 0.1:
            rel_pos = "AT_SPOT"
        elif dist_pts > 0:
            rel_pos = "ABOVE_SPOT"
        else:
            rel_pos = "BELOW_SPOT"

        price_display = f"{start_p:,.2f}"
        if end_p is not None and abs(end_p - start_p) > 0.01:
            price_display = f"{start_p:,.2f} - {end_p:,.2f}"

        items.append(QuantLevelItem(
            start_price=start_p,
            end_price=end_p,
            price_display=price_display,
            type=lvl_type,
            comments=comments,
            web_link=web_link,
            distance_pts=dist_pts,
            distance_pct=dist_pct,
            relative_position=rel_pos
        ))

    # Identify immediate support & resistance
    # items are sorted start_price DESC
    imm_res: Optional[QuantLevelItem] = None
    imm_sup: Optional[QuantLevelItem] = None

    for item in reversed(items):
        mid_p = (item.start_price + item.end_price) / 2.0 if item.end_price else item.start_price
        if mid_p >= ref_spot:
            imm_res = item
            break

    for item in items:
        mid_p = (item.start_price + item.end_price) / 2.0 if item.end_price else item.start_price
        if mid_p <= ref_spot:
            imm_sup = item
            break

    if imm_res:
        imm_res.is_immediate_resistance = True
    if imm_sup:
        imm_sup.is_immediate_support = True

    imm_res_val = imm_res.start_price if imm_res else None
    imm_sup_val = imm_sup.start_price if imm_sup else None
    channel_w = round(imm_res_val - imm_sup_val, 2) if (imm_res_val and imm_sup_val) else None

    summary = QuantLevelSummary(
        ticker=clean_ticker,
        as_of_date=str(target_date) if target_date else None,
        spot_price=spot_price,
        immediate_resistance=imm_res_val,
        immediate_support=imm_sup_val,
        channel_width=channel_w,
        total_levels=len(items),
        buy_levels_count=buy_count,
        sell_levels_count=sell_count
    )

    return QuantLevelDataResponse(
        status="ok",
        ticker=clean_ticker,
        as_of_date=str(target_date) if target_date else None,
        available_dates=available_dates,
        spot_price=spot_price,
        summary=summary,
        levels=items
    )
