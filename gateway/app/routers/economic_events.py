"""
Economic Events API Router for Quant Gateway.
Provides endpoints to query stored macroeconomic events (with RAG summaries) and trigger sync cycles.
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field
import pandas as pd

from common_lib.config.main_config import load_config
from common_lib.connectors import postgres
from app.core.auth import get_current_user

logger = logging.getLogger("quant.gateway.economic_events")

router = APIRouter(prefix="/api/economic-events", tags=["Economic Events & Macro RAG Feed"])

# In-memory cooldown timestamp to prevent upstream rate-limit spam
_LAST_SYNC_TIMESTAMP: float = 0.0
_SYNC_COOLDOWN_SECONDS: float = 60.0


class EconomicEventItem(BaseModel):
    event_id: str
    event_timestamp: str
    country: str
    title: str
    impact_tier: str
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    synthetic_summary: str
    status: str = Field(description="'RELEASED' if actual is present, else 'UPCOMING'")


class EconomicEventsListResponse(BaseModel):
    status: str
    count: int
    events: List[EconomicEventItem]


class EconomicEventsSyncResponse(BaseModel):
    status: str
    message: str
    result: Optional[Dict[str, Any]] = None


class MacroEventCardItem(BaseModel):
    event_id: str
    event_timestamp: str
    country: str
    title: str
    impact_tier: str
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    synthetic_summary: str
    status: str
    countdown_seconds: int = Field(description="Seconds until event, negative if past")
    similarity_score: Optional[float] = None


class MacroEventsResponse(BaseModel):
    status: str
    ticker: str
    country: str
    count: int
    events: List[MacroEventCardItem]
    sensitivity_profile: Optional[Dict[str, Any]] = None


class RagContextResponse(BaseModel):
    status: str
    ticker: str
    count: int
    context_block: str
    events: List[Dict[str, Any]]



def _clean_str_field(val: Any) -> Optional[str]:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if s.lower() in ("", "none", "nan", "<na>"):
        return None
    return s


def _run_sync(force: bool = False) -> Dict[str, Any]:
    """Invokes economic events sync service via common_lib."""
    from common_lib.economic_events import run_economic_events_sync
    from app.config import settings
    return run_economic_events_sync(force_refresh=force, api_key=settings.GEMINI_API_KEY)


@router.get("", response_model=EconomicEventsListResponse, summary="Query Economic Events & RAG Chunks")
def list_economic_events(
    country: Optional[str] = Query(None, description="Country or currency filter (e.g. USD, EUR, JPY)"),
    min_impact: str = Query("Medium", description="Minimum impact tier: High, Medium, Low, or All"),
    start_date: Optional[str] = Query(None, description="Start date ISO string (e.g. 2026-09-20)"),
    end_date: Optional[str] = Query(None, description="End date ISO string (e.g. 2026-09-30)"),
    limit: int = Query(50, ge=1, le=500, description="Max events to return")
):
    """
    Returns stored macroeconomic events with pre-rendered RAG context summaries,
    filtered by country, impact tier, and date range.
    """
    try:
        cfg = load_config()
        country_list = [c.strip().upper() for c in country.split(",") if c.strip()] if country else None

        df = postgres.get_economic_events(
            config_or_engine=cfg,
            start_date=start_date,
            end_date=end_date,
            country=country_list,
            min_impact=min_impact,
            limit=limit
        )

        if df.empty:
            return EconomicEventsListResponse(status="ok", count=0, events=[])

        items = []
        for _, row in df.iterrows():
            actual_val = _clean_str_field(row.get("ACTUAL"))
            ts = row.get("EVENT_TIMESTAMP")
            ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)

            items.append(EconomicEventItem(
                event_id=str(row.get("EVENT_ID", "")),
                event_timestamp=ts_str,
                country=str(row.get("COUNTRY", "")),
                title=str(row.get("TITLE", "")),
                impact_tier=str(row.get("IMPACT_TIER", "Low")),
                forecast=_clean_str_field(row.get("FORECAST")),
                previous=_clean_str_field(row.get("PREVIOUS")),
                actual=actual_val,
                synthetic_summary=str(row.get("SYNTHETIC_SUMMARY", "")),
                status="RELEASED" if actual_val else "UPCOMING"
            ))

        return EconomicEventsListResponse(
            status="ok",
            count=len(items),
            events=items
        )
    except Exception as ex:
        logger.error(f"Error fetching economic events: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query economic events: {str(ex)}"
        )


@router.post("/sync", response_model=EconomicEventsSyncResponse, summary="Trigger On-Demand Economic Calendar Ingestion")
def sync_economic_events(
    force: bool = Query(False, description="Force refresh ignoring disk cache")
):
    """
    Triggers the economic events extraction, transformation, and database loading cycle.
    Enforces a 60-second cooldown to protect upstream calendar feeds.
    """
    global _LAST_SYNC_TIMESTAMP
    now = time.time()
    elapsed = now - _LAST_SYNC_TIMESTAMP

    if not force and elapsed < _SYNC_COOLDOWN_SECONDS:
        remaining = int(_SYNC_COOLDOWN_SECONDS - elapsed)
        return EconomicEventsSyncResponse(
            status="throttled",
            message=f"Sync cooldown active. Please wait {remaining}s before triggering another refresh."
        )

    try:
        result = _run_sync(force=force)
        _LAST_SYNC_TIMESTAMP = now
        return EconomicEventsSyncResponse(
            status="success",
            message="Economic events ingestion cycle completed.",
            result=result
        )
    except Exception as ex:
        logger.error(f"Failed to execute economic events sync: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Economic events sync failed: {str(ex)}"
        )


@router.get("/macro", response_model=MacroEventsResponse, summary="Get Macro Events Cards for UI")
def get_macro_events_cards(
    ticker: str = Query("SPY", description="Ticker symbol to query relevant macro events"),
    query: Optional[str] = Query(None, description="Optional custom semantic risk query"),
    limit: int = Query(20, ge=1, le=100, description="Max events to return")
):
    """
    Returns upcoming events for a given ticker, enriched with countdown timers,
    impact badges, and semantic relevance scores for the Macro PWA tab.
    """
    try:
        from common_lib.database.postgres import get_postgres_engine
        from common_lib.economic_events.retrieval import retrieve_relevant_events, get_ticker_currency

        cfg = load_config()
        engine = get_postgres_engine(cfg)
        clean_ticker = ticker.strip().upper()
        country = get_ticker_currency(clean_ticker)

        from app.config import settings

        raw_events = retrieve_relevant_events(
            engine=engine,
            ticker=clean_ticker,
            semantic_query=query,
            api_key=settings.GEMINI_API_KEY,
            top_k=limit
        )

        now_utc = datetime.now(timezone.utc)
        items = []
        for ev in raw_events:
            ts_val = ev.get("event_timestamp")
            if isinstance(ts_val, str):
                try:
                    dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                except Exception:
                    dt = now_utc
            elif isinstance(ts_val, datetime):
                dt = ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
            else:
                dt = now_utc

            countdown_sec = int((dt - now_utc).total_seconds())

            items.append(MacroEventCardItem(
                event_id=str(ev.get("event_id", "")),
                event_timestamp=ev.get("event_timestamp", ""),
                country=str(ev.get("country", country)),
                title=str(ev.get("title", "")),
                impact_tier=str(ev.get("impact_tier", "Low")),
                forecast=_clean_str_field(ev.get("forecast")),
                previous=_clean_str_field(ev.get("previous")),
                actual=_clean_str_field(ev.get("actual")),
                synthetic_summary=str(ev.get("synthetic_summary", "")),
                status=str(ev.get("status", "UPCOMING")),
                countdown_seconds=countdown_sec,
                similarity_score=ev.get("similarity_score")
            ))

        # Fetch dynamic sensitivity profile
        from common_lib.economic_events.sensitivities import get_or_compute_sensitivity
        try:
            sensitivity_profile = get_or_compute_sensitivity(engine, clean_ticker)
            # convert datetimes to strings if any for json serialization
            if sensitivity_profile and "last_calculated_at" in sensitivity_profile:
                if isinstance(sensitivity_profile["last_calculated_at"], datetime):
                    sensitivity_profile["last_calculated_at"] = sensitivity_profile["last_calculated_at"].isoformat()
        except Exception as e:
            logger.warning(f"Could not load sensitivity for {clean_ticker}: {e}")
            sensitivity_profile = None

        return MacroEventsResponse(
            status="ok",
            ticker=clean_ticker,
            country=country,
            count=len(items),
            events=items,
            sensitivity_profile=sensitivity_profile
        )
    except Exception as ex:
        logger.error(f"Error fetching macro cards for {ticker}: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch macro events cards: {str(ex)}"
        )


@router.get("/rag-context", response_model=RagContextResponse, summary="Get Formatted RAG Context Block for LLM")
def get_rag_context_block(
    ticker: str = Query("SPY", description="Ticker symbol"),
    query: Optional[str] = Query(None, description="Optional custom semantic risk query"),
    top_k: int = Query(5, ge=1, le=20, description="Max events to retrieve")
):
    """
    Returns the Top-K relevant macroeconomic context block formatted
    specifically for AI prompt injection.
    """
    try:
        from common_lib.database.postgres import get_postgres_engine
        from common_lib.economic_events.retrieval import retrieve_relevant_events, format_rag_context_block
        from app.config import settings

        cfg = load_config()
        engine = get_postgres_engine(cfg)
        clean_ticker = ticker.strip().upper()

        events = retrieve_relevant_events(
            engine=engine,
            ticker=clean_ticker,
            semantic_query=query,
            api_key=settings.GEMINI_API_KEY,
            top_k=top_k
        )

        context_block = format_rag_context_block(events)

        return RagContextResponse(
            status="ok",
            ticker=clean_ticker,
            count=len(events),
            context_block=context_block,
            events=events
        )
    except Exception as ex:
        logger.error(f"Error building RAG context for {ticker}: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build RAG context: {str(ex)}"
        )


@router.get("/sensitivity", summary="Get Company Macro-Sensitivity Profile")
def get_sensitivity_profile(
    ticker: str = Query("SPY", description="Ticker symbol to query sensitivity profile"),
    force_refresh: bool = Query(False, description="Force re-computation of sensitivities")
):
    try:
        from common_lib.database.postgres import get_postgres_engine
        from common_lib.economic_events.sensitivities import get_or_compute_sensitivity

        cfg = load_config()
        engine = get_postgres_engine(cfg)
        clean_ticker = ticker.strip().upper()

        profile = get_or_compute_sensitivity(engine, clean_ticker, force_refresh=force_refresh)
        
        if profile and "last_calculated_at" in profile and isinstance(profile["last_calculated_at"], datetime):
            profile["last_calculated_at"] = profile["last_calculated_at"].isoformat()
            
        return {
            "status": "ok",
            "ticker": clean_ticker,
            "sensitivity_profile": profile
        }
    except Exception as ex:
        logger.error(f"Error fetching sensitivity for {ticker}: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sensitivity profile: {str(ex)}"
        )
