import json
import logging
import asyncio
import math
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import pandas as pd
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.engine.service import gexdex_service, get_strike_distribution
from app.core.synthesis import synthesis_registry

logger = logging.getLogger("quant.gateway.cockpit")

router = APIRouter(tags=["Cockpit"])


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively replaces NaN, Inf, and -Inf with None / 0.0 to ensure 100% JSON compliance."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_for_json(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_sanitize_for_json(item) for item in obj)
    return obj


class CockpitRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol (e.g. NVDA, SPY, AAPL)")
    payload: Optional[Dict[str, Any]] = Field(None, description="Optional pre-computed Cockpit payload to prevent duplicate recalculation")
    force_refresh: Optional[bool] = Field(False, description="Bypass in-memory cache and force fresh data fetch")


def _fetch_postgres_flow_sync(symbol: str, lookback_days: int = 30, limit: int = 500) -> pd.DataFrame:
    """Synchronous worker to query unusual options flow prints from PostgreSQL connector."""
    try:
        from common_lib.config.main_config import load_config
        config = load_config()
        from common_lib.connectors.postgres import get_unusual_flow as pg_get_flow
        return pg_get_flow(
            config=config,
            symbol=symbol,
            lookback_days=lookback_days,
            limit=limit
        )
    except Exception as ex:
        logger.warning(f"Error querying Postgres unusual flow for {symbol}: {ex}")
        return pd.DataFrame()


def _calculate_cockpit_metrics(gex_data: Dict[str, Any], flow_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
    """Calculates quantitative microstructure metrics, flow aggregates, and confluence bias."""
    spot_price = float(gex_data.get("spot_price", 0.0) or 0.0)
    zero_gamma_flip = float(gex_data.get("zero_gex_level", 0.0) or gex_data.get("zero_gamma_flip", 0.0) or spot_price)
    call_wall = float(gex_data.get("call_wall", 0.0) or 0.0)
    put_wall = float(gex_data.get("put_wall", 0.0) or 0.0)
    net_gex = float(gex_data.get("net_gex", 0.0) or 0.0)
    net_dex = float(gex_data.get("net_dex", 0.0) or 0.0)
    gamma_regime = str(gex_data.get("gamma_regime", "Neutral / Undefined"))

    if flow_df is not None and isinstance(flow_df, pd.DataFrame) and not flow_df.empty:
        call_mask = flow_df["ORDER_TYPE"].str.contains("CALL", case=False, na=False) if "ORDER_TYPE" in flow_df.columns else pd.Series(False, index=flow_df.index)
        put_mask = flow_df["ORDER_TYPE"].str.contains("PUT", case=False, na=False) if "ORDER_TYPE" in flow_df.columns else pd.Series(False, index=flow_df.index)

        prem_series = pd.to_numeric(flow_df["PREMIUM"], errors="coerce").fillna(0.0) if "PREMIUM" in flow_df.columns else pd.Series(0.0, index=flow_df.index)

        total_flow_vol = float(prem_series.sum())
        call_flow = float(prem_series[call_mask].sum())
        put_flow = float(prem_series[put_mask].sum())

        call_pct = round((call_flow / total_flow_vol * 100.0), 2) if total_flow_vol > 0 else 0.0
        put_pct = round((put_flow / total_flow_vol * 100.0), 2) if total_flow_vol > 0 else 0.0

        whale_count = int((prem_series >= 1_000_000.0).sum())

        if "IS_UNUSUAL_OI" in flow_df.columns:
            unusual_oi_count = int(flow_df["IS_UNUSUAL_OI"].isin([1, True, "1", "true", "True"]).sum())
        else:
            unusual_oi_count = 0
    else:
        total_flow_vol = 0.0
        call_flow = 0.0
        put_flow = 0.0
        call_pct = 0.0
        put_pct = 0.0
        whale_count = 0
        unusual_oi_count = 0

    # High-level Confluence Bias: 'BULLISH CONFLUENCE', 'BEARISH CONFLUENCE', or 'NEUTRAL PIN'
    is_gamma_bullish = (net_gex > 0 and spot_price >= zero_gamma_flip) or (net_dex > 0)
    is_gamma_bearish = (net_gex < 0 and spot_price <= zero_gamma_flip) or (net_dex < 0)

    if (call_pct >= 55.0 and is_gamma_bullish) or (call_pct >= 65.0):
        confluence_bias = "BULLISH CONFLUENCE"
    elif (put_pct >= 55.0 and is_gamma_bearish) or (put_pct >= 65.0):
        confluence_bias = "BEARISH CONFLUENCE"
    else:
        confluence_bias = "NEUTRAL PIN"

    return {
        "spot_price": round(spot_price, 2),
        "zero_gamma_flip": round(zero_gamma_flip, 2),
        "call_wall": round(call_wall, 2),
        "put_wall": round(put_wall, 2),
        "net_gex": round(net_gex, 2),
        "net_dex": round(net_dex, 2),
        "gamma_regime": gamma_regime,
        "total_30d_flow_volume": round(total_flow_vol, 2),
        "call_flow": round(call_flow, 2),
        "put_flow": round(put_flow, 2),
        "call_pct": call_pct,
        "put_pct": put_pct,
        "whale_count": whale_count,
        "unusual_oi_count": unusual_oi_count,
        "confluence_bias": confluence_bias
    }


def _format_flow_records(flow_df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
    """Converts DataFrame rows into JSON-serializable records."""
    if flow_df is None or not isinstance(flow_df, pd.DataFrame) or flow_df.empty:
        return []

    # Replace all NaN, Inf, -Inf with None safely
    df_clean = flow_df.astype(object).where(pd.notna(flow_df), None).copy()
    for col in df_clean.columns:
        if pd.api.types.is_datetime64_any_dtype(flow_df[col]):
            df_clean[col] = flow_df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        elif col in ("TRADE_DATE", "EXPIRATION_DATE", "CREATED_AT"):
            df_clean[col] = df_clean[col].astype(str)

    records = df_clean.to_dict(orient="records")
    return _sanitize_for_json(records)


async def get_cockpit_full_payload(ticker: str, force_refresh: bool = False) -> Dict[str, Any]:
    """Concurrently fetches GEX/DEX data and Postgres 30-Day Flow data, returning assembled cockpit payload."""
    clean_ticker = str(ticker).strip().upper().replace("$", "")
    if not clean_ticker:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticker symbol cannot be empty."
        )

    # Concurrently execute full strike distribution calculation and DB options flow query
    gex_task = asyncio.create_task(asyncio.to_thread(get_strike_distribution, clean_ticker, 50, 25, force_refresh))
    flow_task = asyncio.create_task(asyncio.to_thread(_fetch_postgres_flow_sync, clean_ticker, 30, 500))

    gex_result, flow_result = await asyncio.gather(gex_task, flow_task, return_exceptions=True)

    if isinstance(gex_result, Exception):
        logger.error(f"GEX/DEX query exception for {clean_ticker}: {gex_result}")
        gex_data = {"error": str(gex_result), "ticker": clean_ticker, "spot_price": 0.0, "strikes": []}
    elif hasattr(gex_result, "model_dump"):
        gex_data = gex_result.model_dump()
    elif hasattr(gex_result, "dict"):
        gex_data = gex_result.dict()
    elif isinstance(gex_result, dict):
        gex_data = gex_result
    else:
        gex_data = {}

    if isinstance(flow_result, Exception):
        logger.error(f"Postgres flow query exception for {clean_ticker}: {flow_result}")
        flow_df = pd.DataFrame()
    else:
        flow_df = flow_result if isinstance(flow_result, pd.DataFrame) else pd.DataFrame()

    # Defense-in-depth: Filter out invalid / phantom zero-strike options prints
    if not flow_df.empty:
        strike_col = None
        for col in ["STRIKE_PRICE", "strike_price", "STRIKE", "strike"]:
            if col in flow_df.columns:
                strike_col = col
                break
        if strike_col:
            numeric_strikes = pd.to_numeric(flow_df[strike_col], errors="coerce")
            flow_df = flow_df[numeric_strikes > 0].copy()

    metrics = _calculate_cockpit_metrics(gex_data, flow_df)
    flow_records = _format_flow_records(flow_df)

    raw_payload = {
        "ticker": clean_ticker,
        "status": "ok",
        "gex": gex_data,
        "flow": {
            "records": flow_records,
            "total_count": len(flow_records)
        },
        "metrics": metrics
    }
    synthesis_markdown = ""
    try:
        synthesis_markdown = synthesis_registry.generate_deterministic_synthesis(clean_ticker, raw_payload)
    except Exception as synth_err:
        logger.warning(f"Error generating deterministic synthesis for {clean_ticker}: {synth_err}")
    raw_payload["synthesis_markdown"] = synthesis_markdown

    return _sanitize_for_json(raw_payload)


@router.get("/data", summary="Get Ticker Cockpit Data (GET)")
async def get_cockpit_data_get(ticker: str, force_refresh: bool = False):
    """Retrieves complete multi-source Ticker Cockpit data via GET."""
    clean_ticker = (ticker or "").strip().upper().replace("$", "")
    if not clean_ticker:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticker symbol cannot be empty."
        )
    payload = await get_cockpit_full_payload(clean_ticker, force_refresh=force_refresh)
    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.post("/data", summary="Get Ticker Cockpit Data (POST)")
async def get_cockpit_data_post(req: CockpitRequest):
    """Retrieves complete multi-source Ticker Cockpit data via POST."""
    clean_ticker = req.ticker.strip().upper().replace("$", "")
    if not clean_ticker:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticker symbol cannot be empty."
        )
    payload = await get_cockpit_full_payload(clean_ticker, force_refresh=bool(req.force_refresh))
    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


from app.core.synthesis import synthesis_registry


def _build_synthesis_prompt(ticker: str, payload: Dict[str, Any]) -> str:
    """Constructs prompt for Gemini demanding the 3-Tier Tactical Playbook."""
    return synthesis_registry.build_synthesis_prompt(ticker, payload)


def _generate_deterministic_synthesis(ticker: str, payload: Dict[str, Any]) -> str:
    """Fallback deterministic synthesis generator when Gemini API is offline or unconfigured."""
    return synthesis_registry.generate_deterministic_synthesis(ticker, payload)



@router.get("/synthesis/stream", summary="Stream Cockpit Tactical Synthesis (GET)")
async def stream_cockpit_synthesis_get(request: Request, ticker: str):
    """Streams real-time 3-Tier Tactical Playbook synthesis via GET SSE."""
    clean_ticker = (ticker or "").strip().upper().replace("$", "")
    if not clean_ticker:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticker symbol cannot be empty."
        )
    return await _stream_synthesis_impl(request, clean_ticker)


@router.post("/synthesis/stream", summary="Stream Cockpit Tactical Synthesis (POST)")
async def stream_cockpit_synthesis_post(request: Request, req: CockpitRequest):
    """Streams real-time 3-Tier Tactical Playbook synthesis via POST SSE."""
    clean_ticker = req.ticker.strip().upper().replace("$", "")
    if not clean_ticker:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticker symbol cannot be empty."
        )
    return await _stream_synthesis_impl(request, clean_ticker, precomputed_payload=req.payload)


async def _stream_synthesis_impl(request: Request, clean_ticker: str, precomputed_payload: Optional[Dict[str, Any]] = None):
    # 1. Fetch cockpit data payload (use pre-computed if valid to avoid duplicate server calculation)
    if precomputed_payload and isinstance(precomputed_payload, dict) and precomputed_payload.get("metrics"):
        logger.info(f"Using pre-computed Cockpit payload for {clean_ticker} synthesis stream (0ms compute overhead)")
        cockpit_payload = precomputed_payload
    else:
        logger.info(f"Computing Cockpit payload on the fly for {clean_ticker} synthesis stream")
        cockpit_payload = await get_cockpit_full_payload(clean_ticker)

    async def sse_generator():
        try:
            # Deterministic quantitative synthesis (0ms LLM latency)
            synth_text = cockpit_payload.get("synthesis_markdown") or _generate_deterministic_synthesis(clean_ticker, cockpit_payload)
            payload_json = json.dumps({"type": "token", "content": synth_text})
            yield f"data: {payload_json}\n\n"
            yield "data: [DONE]\n\n"
            return
        except Exception as e:
            logger.error(f"Synthesis stream failure for {clean_ticker}: {e}")
            err_payload = json.dumps({"type": "error", "message": str(e)})
            yield f"data: {err_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
