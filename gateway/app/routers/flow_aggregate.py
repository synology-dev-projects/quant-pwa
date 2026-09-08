import logging
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import StreamingResponse
import sqlalchemy as sa
import pandas as pd

from app.config import settings
from app.core.auth import get_current_user
from app.routers.flow_status import get_last_market_day
from app.core.flow_synthesis import flow_synthesis_registry

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


@router.post("/synthesis/stream")
@router.get("/synthesis/stream")
async def stream_flow_synthesis(
    request: Request,
    as_of_date: Optional[str] = Query(None, description="Anchor trade date (YYYY-MM-DD)"),
    _: str = Depends(get_current_user)
):
    """
    Streams the Flow Executive Synthesis (Notable Flow) using Gemini API or deterministic fallback.
    Delivers Server-Sent Events (SSE) tokens for real-time rendering on the Flow Hero Card.
    """
    async def sse_generator():
        try:
            # 1. Resolve target session date and database engine
            target_date = as_of_date
            features = {}
            try:
                engine = _get_engine()
                with engine.connect() as conn:
                    if not target_date:
                        last_mkt_day = str(get_last_market_day())
                        date_query = sa.text("""
                            SELECT DISTINCT trade_date
                            FROM unusual_option_flow_te
                            WHERE trade_date <= :last_market_day
                              AND strike_price > 0
                            ORDER BY trade_date DESC
                            LIMIT 1
                        """)
                        row = conn.execute(date_query, {"last_market_day": last_mkt_day}).first()
                        if not row:
                            fallback_query = sa.text("""
                                SELECT DISTINCT trade_date
                                FROM unusual_option_flow_te
                                WHERE strike_price > 0
                                ORDER BY trade_date DESC
                                LIMIT 1
                            """)
                            row = conn.execute(fallback_query).first()
                        target_date = str(row[0]) if row else str(date.today())

                    features = flow_synthesis_registry.extract_all_features(conn, target_date)
            except Exception as db_err:
                logger.warning(f"Database error while extracting flow synthesis features: {db_err}")
                target_date = target_date or str(date.today())
                features = {}

            # 2. Try Gemini API Streaming if configured
            if settings.GEMINI_API_KEY:
                try:
                    from google import genai
                    from google.genai import types

                    prompt = flow_synthesis_registry.build_synthesis_prompt(target_date, features)
                    client = genai.Client(
                        api_key=settings.GEMINI_API_KEY,
                        http_options=types.HttpOptions(timeout=60000, retry_options=types.HttpRetryOptions(attempts=1))
                    )

                    model_name = settings.TIER1_FAST_WORKER_MODEL or "gemini-3.5-flash-lite"
                    gen_config = types.GenerateContentConfig(
                        temperature=0.2,
                        system_instruction="You are Quant AI, an elite institutional options flow strategist."
                    )

                    response_stream = await client.aio.models.generate_content_stream(
                        model=model_name,
                        contents=prompt,
                        config=gen_config
                    )

                    async for chunk in response_stream:
                        if await request.is_disconnected():
                            logger.info("Client disconnected during flow synthesis stream")
                            return
                        if chunk.text:
                            payload_json = json.dumps({"type": "token", "content": chunk.text})
                            yield f"data: {payload_json}\n\n"

                    yield "data: [DONE]\n\n"
                    return
                except Exception as genai_err:
                    logger.warning(f"Gemini API error during flow synthesis: {genai_err}. Falling back to deterministic generator.")

            # 3. Fallback deterministic generator
            fallback_text = flow_synthesis_registry.generate_deterministic_synthesis(features)
            words = fallback_text.split(" ")
            for i, word in enumerate(words):
                if await request.is_disconnected():
                    return
                space = " " if i < len(words) - 1 else ""
                token_payload = json.dumps({"type": "token", "content": word + space})
                yield f"data: {token_payload}\n\n"
                await asyncio.sleep(0.005)

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Flow synthesis streaming failure: {e}", exc_info=True)
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

