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
    return run_economic_events_sync(force_refresh=force)


@router.get("", response_model=EconomicEventsListResponse, summary="Query Economic Events & RAG Chunks")
async def list_economic_events(
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
async def sync_economic_events(
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
