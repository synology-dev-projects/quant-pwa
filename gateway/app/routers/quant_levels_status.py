import logging
import time as time_module
from datetime import datetime, date, timedelta, time, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Any, List, Dict, Tuple
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import pandas as pd

from common_lib.config.main_config import load_config
from common_lib.connectors import postgres
from app.core.auth import get_current_user
from app.core.quote_feed import get_batch_quotes

logger = logging.getLogger("quant.gateway.quant_levels_status")

router = APIRouter(tags=["Quant Levels Ingestion Status"])

_CANDLES_CACHE: Dict[str, Tuple[float, List["CandlestickBar"]]] = {}


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


class QuantLevelExtractDateResponse(BaseModel):
    status: str
    target_date: str
    rows_upserted: int
    message: str


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


class MacroItem(BaseModel):
    symbol: str
    label: str
    price: float
    change: float = 0.0
    change_pct: float = 0.0
    regime_tag: str
    sentiment: str  # "BULLISH", "BEARISH", "NEUTRAL"
    updated_at: Optional[str] = None


class MacroCorrelationContext(BaseModel):
    vix: Optional[MacroItem] = None
    us10y: Optional[MacroItem] = None
    composite_regime: str
    spx_reaction: str  # "BULLISH_SUPPORTIVE", "BEARISH_PRESSURE", "NEUTRAL_CONSOLIDATION"
    reaction_label: str  # "RISK-ON TAILWINDS", "VOL SPIKE / CAUTION", "RATE PRESSURE", etc.


class QuantLevelSummary(BaseModel):
    ticker: str
    as_of_date: Optional[str] = None
    spot_price: Optional[float] = None
    spot_type: str = "LIVE"
    spot_label: str = "SPX Live Spot"
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
    spot_type: str = "LIVE"
    spot_label: str = "SPX Live Spot"
    summary: QuantLevelSummary
    levels: List[QuantLevelItem] = []
    macro_context: Optional[MacroCorrelationContext] = None
    message: Optional[str] = None


class CandlestickBar(BaseModel):
    timestamp: int
    datetime: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[int] = 0


class QuantLevelCandlesResponse(BaseModel):
    status: str
    ticker: str
    as_of_date: str
    session_open: Optional[float] = None
    session_close: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    session_change_pts: Optional[float] = None
    session_change_pct: Optional[float] = None
    candles: List[CandlestickBar] = []
    message: Optional[str] = None


class LevelAlertItem(BaseModel):
    id: str
    ticker: str
    level_price: float
    level_type: str  # "BUY" or "SELL"
    current_spot: float
    distance_pts: float
    comments: Optional[str] = None
    timestamp: str
    session_date: Optional[str] = None
    level_price_range: Optional[str] = None
    touched_boundary: Optional[float] = None


class LevelAlertPendingCooldown(BaseModel):
    level_price: float
    level_type: str = "ALERT"
    cooldown_remaining_sec: int
    triggered_at: str


class LevelAlertMonitorStatusResponse(BaseModel):
    active: bool
    is_market_hours: bool
    market_session: str
    last_check_timestamp: Optional[str] = None
    last_spot_price: Optional[float] = None
    monitored_levels_count: int = 0
    active_cooldowns_count: int = 0
    pending_cooldowns: List[LevelAlertPendingCooldown] = []


class LevelAlertsRecentResponse(BaseModel):
    status: str = "success"
    count: int = 0
    alerts: List[LevelAlertItem] = []


class TestAlertRequest(BaseModel):
    test_spot: float = 6020.85
    test_level: float = 6020.00
    level_type: str = "BUY"
    comments: Optional[str] = "Synthetic test alert triggered via REST API"
    level_price_range: Optional[str] = None
    touched_boundary: Optional[float] = None


class TestAlertResponse(BaseModel):
    status: str
    message: str
    alert: LevelAlertItem


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


def compute_macro_correlation(quotes: Dict[str, Dict[str, Any]], spx_price: Optional[float] = None) -> MacroCorrelationContext:
    """
    Computes real-time cross-asset macro correlation context between SPX, VIX volatility,
    and the 10-Year Treasury Yield (^TNX).
    """
    # 1. Parse VIX quote
    vix_quote = quotes.get("^VIX") or quotes.get("VIX")
    vix_item: Optional[MacroItem] = None
    vix_sentiment = "NEUTRAL"
    if vix_quote and vix_quote.get("price") is not None:
        v_price = float(vix_quote["price"])
        v_change = float(vix_quote.get("change", 0.0))
        v_pct = float(vix_quote.get("change_pct", 0.0))

        if v_price < 13.5:
            regime = "EXTREME COMPRESSION"
            vix_sentiment = "BULLISH"
        elif v_price < 17.5:
            regime = "SUBDUED / FAVORABLE"
            vix_sentiment = "BULLISH" if v_change <= 0 else "NEUTRAL"
        elif v_price < 22.0:
            regime = "ELEVATED / CAUTION"
            vix_sentiment = "BEARISH" if v_change > 0 else "NEUTRAL"
        else:
            regime = "HIGH VOLATILITY"
            vix_sentiment = "BEARISH"

        if v_pct >= 5.0:
            regime += " (SPIKING)"
        elif v_pct <= -5.0:
            regime += " (CRUSHING)"

        vix_item = MacroItem(
            symbol="^VIX",
            label="VIX",
            price=round(v_price, 2),
            change=round(v_change, 2),
            change_pct=round(v_pct, 2),
            regime_tag=regime,
            sentiment=vix_sentiment,
            updated_at=vix_quote.get("updated_at")
        )

    # 2. Parse 10-Year Treasury Yield (^TNX) quote
    tnx_quote = quotes.get("^TNX") or quotes.get("TNX")
    tnx_item: Optional[MacroItem] = None
    yield_sentiment = "NEUTRAL"
    if tnx_quote and tnx_quote.get("price") is not None:
        y_val = float(tnx_quote["price"])
        y_change = float(tnx_quote.get("change", 0.0))
        y_pct = float(tnx_quote.get("change_pct", 0.0))

        if y_change > 0.05:
            regime = "YIELD SURGING / HEADWIND"
            yield_sentiment = "BEARISH"
        elif y_change < -0.05:
            regime = "YIELD EASING / TAILWIND"
            yield_sentiment = "BULLISH"
        else:
            regime = "YIELD STABLE / NEUTRAL"
            yield_sentiment = "NEUTRAL"

        tnx_item = MacroItem(
            symbol="^TNX",
            label="10Y YIELD",
            price=round(y_val, 3),
            change=round(y_change, 3),
            change_pct=round(y_pct, 2),
            regime_tag=regime,
            sentiment=yield_sentiment,
            updated_at=tnx_quote.get("updated_at")
        )

    # 3. Composite SPX Cross-Asset Reaction
    if vix_sentiment == "BULLISH" and yield_sentiment in ("BULLISH", "NEUTRAL"):
        spx_reaction = "BULLISH_SUPPORTIVE"
        reaction_label = "RISK-ON TAILWINDS"
        composite = "Vol compressed & yields supportive; favorable for equity expansion"
    elif vix_sentiment == "BEARISH" and yield_sentiment == "BEARISH":
        spx_reaction = "BEARISH_PRESSURE"
        reaction_label = "CROSS-ASSET HEADWINDS"
        composite = "Vol expanding with surging yields; dual cross-asset headwind"
    elif vix_sentiment == "BEARISH":
        spx_reaction = "BEARISH_PRESSURE"
        reaction_label = "VOL SPIKE / HEDGING"
        composite = "Vol expanding; options hedging pressure capping upside"
    elif yield_sentiment == "BEARISH":
        spx_reaction = "BEARISH_PRESSURE"
        reaction_label = "RATE PRESSURE"
        composite = "Yield spike putting valuation multiple pressure on equities"
    elif yield_sentiment == "BULLISH":
        spx_reaction = "BULLISH_SUPPORTIVE"
        reaction_label = "YIELD RELAXATION"
        composite = "Easing Treasury yields providing multiple relief for equities"
    else:
        spx_reaction = "NEUTRAL_CONSOLIDATION"
        reaction_label = "BALANCED REGIME"
        composite = "Macro volatility and yields in equilibrium; range-bound flow"

    return MacroCorrelationContext(
        vix=vix_item,
        us10y=tnx_item,
        composite_regime=composite,
        spx_reaction=spx_reaction,
        reaction_label=reaction_label
    )


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

    # 2. Query quant levels from postgres
    try:
        df_levels = postgres.get_quant_levels(config, ticker=clean_ticker, as_of_date=target_date)
    except Exception as ex:
        logger.error(f"Error querying quant levels for {clean_ticker}: {ex}")
        df_levels = pd.DataFrame()

    # Filter to exact target_date if resolved and DATETIME present
    if target_date is not None and "DATETIME" in df_levels.columns and not df_levels.empty:
        df_levels["DATE_ONLY"] = pd.to_datetime(df_levels["DATETIME"]).dt.date
        date_filtered = df_levels[df_levels["DATE_ONLY"] == target_date].copy()
        if not date_filtered.empty:
            df_levels = date_filtered
        else:
            # Fallback to latest available date in DataFrame
            max_d = pd.to_datetime(df_levels["DATETIME"]).dt.date.max()
            df_levels = df_levels[pd.to_datetime(df_levels["DATETIME"]).dt.date == max_d].copy()
            target_date = max_d
    elif "DATETIME" in df_levels.columns and not df_levels.empty:
        max_d = pd.to_datetime(df_levels["DATETIME"]).dt.date.max()
        df_levels = df_levels[pd.to_datetime(df_levels["DATETIME"]).dt.date == max_d].copy()
        target_date = max_d

    # 3. Spot price resolution (Live vs Historical Close)
    eastern = ZoneInfo("America/New_York")
    now_eastern = datetime.now(eastern)
    is_historical = (target_date is not None and target_date < now_eastern.date())

    spot_price: Optional[float] = None
    macro_context: Optional[MacroCorrelationContext] = None
    if is_historical:
        spot_type = "HISTORICAL_CLOSE"
        spot_label = "SPX Session Close"
        try:
            spot_price = await _get_session_close(target_date)
        except Exception as ex:
            logger.warning(f"Failed resolving historical session close for {target_date}: {ex}")
    else:
        spot_type = "LIVE"
        spot_label = "SPX Live Spot"
        quote_syms = []
        if clean_ticker == "SPX":
            quote_syms.extend(["^GSPC", "^SPX", "SPX"])
        elif clean_ticker == "NDX":
            quote_syms.extend(["^NDX", "^IXIC", "NDX"])
        else:
            quote_syms.append(clean_ticker)

        # Include macro assets in single batch fetch
        quote_syms.extend(["^VIX", "^TNX"])

        try:
            quotes = await get_batch_quotes(quote_syms)
            for sym in quote_syms:
                if sym not in ("^VIX", "^TNX") and sym in quotes and quotes[sym].get("price"):
                    spot_price = float(quotes[sym]["price"])
                    break
            macro_context = compute_macro_correlation(quotes, spot_price)
        except Exception as ex:
            logger.warning(f"Failed fetching quotes for {clean_ticker}: {ex}")

        # If live quote feed failed, fallback to latest intraday candle close
        if spot_price is None and clean_ticker == "SPX":
            try:
                today_eastern = now_eastern.date()
                bars = await _get_candles_bars(today_eastern)
                if bars:
                    spot_price = bars[-1].close
            except Exception as ex:
                logger.warning(f"Failed falling back to latest candle close for {clean_ticker}: {ex}")

    # 4. Cross-Asset Macro Correlation Context (^VIX & ^TNX) fallback if historical
    if macro_context is None:
        try:
            macro_quotes = await get_batch_quotes(["^VIX", "^TNX"])
            macro_context = compute_macro_correlation(macro_quotes, spot_price)
        except Exception as ex:
            logger.warning(f"Failed resolving macro correlation context: {ex}")

    if df_levels.empty:
        summary = QuantLevelSummary(
            ticker=clean_ticker,
            as_of_date=str(target_date) if target_date else None,
            spot_price=spot_price,
            spot_type=spot_type,
            spot_label=spot_label,
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
            spot_type=spot_type,
            spot_label=spot_label,
            summary=summary,
            levels=[],
            macro_context=macro_context,
            message=f"No quant levels found for {clean_ticker} as of {target_date or 'latest'}."
        )

    # Convert to structured items
    items: List[QuantLevelItem] = []
    buy_count = 0
    sell_count = 0

    df_levels["START_LVL_PRICE"] = pd.to_numeric(df_levels["START_LVL_PRICE"], errors="coerce")
    df_levels = df_levels.dropna(subset=["START_LVL_PRICE"])

    # Defensively filter out non-SPX outlier records (e.g. SPY/QQQ levels ~700 from multi-ticker scraper posts)
    if clean_ticker == "SPX":
        df_levels = df_levels[df_levels["START_LVL_PRICE"] >= 2500.0]

    ref_spot = spot_price or (
        float(df_levels["START_LVL_PRICE"].median()) if not df_levels.empty else 0.0
    )
    if ref_spot > 0:
        df_levels = df_levels[
            (df_levels["START_LVL_PRICE"] >= ref_spot * 0.50) &
            (df_levels["START_LVL_PRICE"] <= ref_spot * 1.50)
        ]

    df_levels = df_levels.sort_values(by="START_LVL_PRICE", ascending=False)
    if spot_price is None and is_historical and not df_levels.empty:
        spot_price = ref_spot

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

        comments = str(row.get("COMMENTS")).strip() if pd_not_na(row.get("COMMENTS")) else None
        if comments == "":
            comments = None
        web_link = str(row.get("WEB_LINK")).strip() if pd_not_na(row.get("WEB_LINK")) else None
        if web_link == "":
            web_link = None

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
        spot_type=spot_type,
        spot_label=spot_label,
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
        spot_type=spot_type,
        spot_label=spot_label,
        summary=summary,
        levels=items,
        macro_context=macro_context
    )


def _compute_candle_session_metrics(bars: List[CandlestickBar]) -> Dict[str, Optional[float]]:
    if not bars:
        return {
            "session_open": None,
            "session_close": None,
            "session_high": None,
            "session_low": None,
            "session_change_pts": None,
            "session_change_pct": None,
        }
    s_open = bars[0].open
    s_close = bars[-1].close
    s_high = max(b.high for b in bars)
    s_low = min(b.low for b in bars)
    s_pts = round(s_close - s_open, 2)
    s_pct = round((s_pts / s_open) * 100, 2) if s_open else 0.0
    return {
        "session_open": s_open,
        "session_close": s_close,
        "session_high": s_high,
        "session_low": s_low,
        "session_change_pts": s_pts,
        "session_change_pct": s_pct,
    }


async def _get_candles_bars(target_date: date) -> List[CandlestickBar]:
    clean_ticker = "SPX"
    target_str = target_date.strftime("%Y-%m-%d")
    cache_key = f"{clean_ticker}_{target_str}"
    eastern = ZoneInfo("America/New_York")
    now_eastern = datetime.now(eastern)

    is_today = (target_date >= now_eastern.date())
    ttl = 30.0 if is_today else 86400.0  # 30s for active session, 24h for historical sessions

    # Check in-memory cache
    if cache_key in _CANDLES_CACHE:
        cached_time, cached_bars = _CANDLES_CACHE[cache_key]
        if time_module.time() - cached_time < ttl:
            return cached_bars

    dt_start = datetime(target_date.year, target_date.month, target_date.day, 9, 30, tzinfo=eastern)
    dt_end = datetime(target_date.year, target_date.month, target_date.day, 16, 15, tzinfo=eastern)
    p1 = int(dt_start.timestamp()) - 300
    p2 = int(dt_end.timestamp()) + 300
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?period1={p1}&period2={p2}&interval=5m"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    bars: List[CandlestickBar] = []
    async with httpx.AsyncClient(timeout=6.0) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("chart", {}).get("result", [])
            if results:
                res0 = results[0]
                timestamps = res0.get("timestamp", [])
                indicators = res0.get("indicators", {}).get("quote", [{}])[0]
                opens = indicators.get("open", [])
                highs = indicators.get("high", [])
                lows = indicators.get("low", [])
                closes = indicators.get("close", [])
                volumes = indicators.get("volume", [])

                for i, ts in enumerate(timestamps):
                    if i >= len(opens) or i >= len(highs) or i >= len(lows) or i >= len(closes):
                        break
                    o, h, l, c = opens[i], highs[i], lows[i], closes[i]
                    if o is None or h is None or l is None or c is None:
                        continue
                    bar_dt = datetime.fromtimestamp(ts, eastern)
                    if bar_dt.date() != target_date:
                        continue
                    bar_time = bar_dt.time()
                    if bar_time < time(9, 30) or bar_time > time(16, 15):
                        continue
                    vol = int(volumes[i]) if (i < len(volumes) and volumes[i] is not None) else 0
                    bars.append(CandlestickBar(
                        timestamp=ts,
                        datetime=bar_dt.strftime("%H:%M"),
                        open=round(float(o), 2),
                        high=round(float(h), 2),
                        low=round(float(l), 2),
                        close=round(float(c), 2),
                        volume=vol
                    ))

    _CANDLES_CACHE[cache_key] = (time_module.time(), bars)
    return bars


async def _get_session_close(target_date: date) -> Optional[float]:
    try:
        bars = await _get_candles_bars(target_date)
        if bars:
            return bars[-1].close
    except Exception as ex:
        logger.warning(f"Error getting 5m candles for session close on {target_date}: {ex}")

    # Fallback to 1d Yahoo Finance chart
    try:
        eastern = ZoneInfo("America/New_York")
        dt_start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, tzinfo=eastern)
        dt_end = dt_start + timedelta(days=1)
        p1 = int(dt_start.timestamp()) - 3600
        p2 = int(dt_end.timestamp()) + 3600
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?period1={p1}&period2={p2}&interval=1d"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("chart", {}).get("result", [])
                if results:
                    closes = results[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
                    valid_closes = [c for c in closes if c is not None]
                    if valid_closes:
                        return round(float(valid_closes[-1]), 2)
    except Exception as ex:
        logger.warning(f"Fallback 1d close fetch failed for {target_date}: {ex}")

    return None


@router.get("/candles", response_model=QuantLevelCandlesResponse)
async def get_quant_levels_candles(
    ticker: str = "SPX",
    as_of_date: Optional[str] = None
):
    """
    Fetches 5-minute intraday candlestick bars for SPX for the specified as_of_date
    (or latest available session) from Yahoo Finance (^GSPC) during regular trading hours (09:30 - 16:15 ET).
    Results are cached in memory (24h for historical dates, 30s for active date).
    """
    clean_ticker = "SPX"
    eastern = ZoneInfo("America/New_York")
    now_eastern = datetime.now(eastern)

    target_date: date
    if as_of_date and as_of_date.strip():
        try:
            target_date = datetime.strptime(as_of_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            target_date = get_expected_quant_levels_date(now_eastern)
    else:
        target_date = get_expected_quant_levels_date(now_eastern)

    target_str = target_date.strftime("%Y-%m-%d")

    try:
        bars = await _get_candles_bars(target_date)
        metrics = _compute_candle_session_metrics(bars)
        return QuantLevelCandlesResponse(
            status="ok" if bars else "empty",
            ticker=clean_ticker,
            as_of_date=target_str,
            session_open=metrics["session_open"],
            session_close=metrics["session_close"],
            session_high=metrics["session_high"],
            session_low=metrics["session_low"],
            session_change_pts=metrics["session_change_pts"],
            session_change_pct=metrics["session_change_pct"],
            candles=bars,
            message=None if bars else f"No intraday session candles available for {target_str}."
        )
    except Exception as ex:
        logger.warning(f"Error fetching SPX candles for {target_str}: {ex}")
        return QuantLevelCandlesResponse(
            status="error",
            ticker=clean_ticker,
            as_of_date=target_str,
            session_open=None,
            session_close=None,
            session_high=None,
            session_low=None,
            session_change_pts=None,
            session_change_pct=None,
            candles=[],
            message=f"Failed to retrieve SPX intraday candles: {str(ex)}"
        )


@router.post("/extract-date", response_model=QuantLevelExtractDateResponse)
async def extract_quant_levels_for_date(
    target_date: str,
    current_user: str = Depends(get_current_user)
):
    """
    On-demand targeted quant levels extraction for a specific historical date.
    Auth protected (requires valid session token).
    """
    logger.info(f"User '{current_user}' requested quant levels extraction for target_date='{target_date}'.")

    # Validate target_date format YYYY-MM-DD
    try:
        dt = datetime.strptime(target_date.strip(), "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Expected YYYY-MM-DD."
        )

    try:
        from common_lib.quant_levels.runner import run_target_date_extraction
        config = load_config()
        rows = run_target_date_extraction(dt, config=config)
        return QuantLevelExtractDateResponse(
            status="ok",
            target_date=target_date,
            rows_upserted=rows,
            message=f"Successfully extracted {rows} quant levels for {target_date}."
        )
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Targeted quant levels extraction failed for {target_date}: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Targeted date extraction failed: {str(ex)}"
        )


# ==============================================================================
# SPX QUANT LEVEL PROXIMITY ALERTS ENDPOINTS
# ==============================================================================

@router.get("/alerts/status", response_model=LevelAlertMonitorStatusResponse)
async def get_level_alerts_status():
    """
    Returns real-time diagnostics of the SPX Quant Level Proximity Alert monitor worker.
    """
    from app.engine.level_alert_monitor import level_alert_monitor
    return level_alert_monitor.get_status()


@router.get("/alerts/recent", response_model=LevelAlertsRecentResponse)
async def get_recent_level_alerts(limit: int = 50):
    """
    Returns recent SPX level proximity alerts triggered in the current session (sorted newest first).
    """
    from app.engine.level_alert_monitor import level_alert_monitor
    alerts = level_alert_monitor.get_recent_alerts(limit=limit)
    return LevelAlertsRecentResponse(
        status="success",
        count=len(alerts),
        alerts=alerts
    )


@router.post("/alerts/test", response_model=TestAlertResponse)
async def trigger_test_level_alert(
    payload: Optional[TestAlertRequest] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Dispatches a synthetic test alert through NTFY and registers it in recent alerts history.
    Auth protected via session token.
    """
    from app.engine.level_alert_monitor import level_alert_monitor
    logger.info(f"User '{current_user}' triggered synthetic SPX level alert.")
    spot = payload.test_spot if payload else 6020.85
    level = payload.test_level if payload else 6020.00
    lvl_type = payload.level_type if payload else "BUY"

    alert = level_alert_monitor.trigger_test_alert(
        test_spot=spot,
        test_level=level,
        level_type=lvl_type,
        comments=payload.comments if payload else "Synthetic test alert triggered via REST API",
        level_price_range=payload.level_price_range if payload else None,
        touched_boundary=payload.touched_boundary if payload else None
    )

    return TestAlertResponse(
        status="dispatched",
        message="Test alert sent to NTFY topic 'spx_alerts' and recorded in memory.",
        alert=alert
    )

