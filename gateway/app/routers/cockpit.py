import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import pandas as pd
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.engine.service import gexdex_service, get_strike_distribution

logger = logging.getLogger("quant.gateway.cockpit")

router = APIRouter(tags=["Cockpit"])


class CockpitRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol (e.g. NVDA, SPY, AAPL)")


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

    df_clean = flow_df.where(pd.notna(flow_df), None).copy()
    for col in df_clean.columns:
        if pd.api.types.is_datetime64_any_dtype(df_clean[col]):
            df_clean[col] = df_clean[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        elif col in ("TRADE_DATE", "EXPIRATION_DATE", "CREATED_AT"):
            df_clean[col] = df_clean[col].astype(str)

    return df_clean.to_dict(orient="records")


async def get_cockpit_full_payload(ticker: str) -> Dict[str, Any]:
    """Concurrently fetches GEX/DEX data and Postgres 30-Day Flow data, returning assembled cockpit payload."""
    clean_ticker = str(ticker).strip().upper().replace("$", "")
    if not clean_ticker:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticker symbol cannot be empty."
        )

    # Concurrently execute full strike distribution calculation and DB options flow query
    gex_task = asyncio.create_task(asyncio.to_thread(get_strike_distribution, clean_ticker))
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

    metrics = _calculate_cockpit_metrics(gex_data, flow_df)
    flow_records = _format_flow_records(flow_df)

    return {
        "ticker": clean_ticker,
        "status": "ok",
        "gex": gex_data,
        "flow": {
            "records": flow_records,
            "total_count": len(flow_records)
        },
        "metrics": metrics
    }


@router.get("/data", summary="Get Ticker Cockpit Data (GET)")
async def get_cockpit_data_get(ticker: str):
    """Retrieves complete multi-source Ticker Cockpit data via GET."""
    clean_ticker = (ticker or "").strip().upper().replace("$", "")
    if not clean_ticker:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticker symbol cannot be empty."
        )
    payload = await get_cockpit_full_payload(clean_ticker)
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
    payload = await get_cockpit_full_payload(clean_ticker)
    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


def _build_synthesis_prompt(ticker: str, payload: Dict[str, Any]) -> str:
    """Constructs prompt for Gemini demanding the 3-Tier Tactical Playbook."""
    metrics = payload.get("metrics", {})
    gex = payload.get("gex", {})
    flow = payload.get("flow", {})
    records = flow.get("records", [])

    # Extract top 5 prints for prompt context
    top_prints = []
    if records:
        sorted_records = sorted(records, key=lambda r: float(r.get("PREMIUM") or 0.0), reverse=True)[:5]
        for r in sorted_records:
            t_date = str(r.get("TRADE_DATE", ""))[:10]
            prem = float(r.get("PREMIUM") or 0.0)
            order_type = str(r.get("ORDER_TYPE", "")).replace("_", " ")
            strike = r.get("STRIKE_PRICE", "N/A")
            exp = str(r.get("EXPIRATION_DATE", ""))[:10]
            oi = r.get("OPEN_INTEREST", 0)
            unusual = " ⚠️" if r.get("IS_UNUSUAL_OI") in (1, True, "1") else ""
            top_prints.append(f"  • {t_date}: ${prem:,.0f} {order_type} | Strike: ${strike} | Exp: {exp} | OI: {oi}{unusual}")

    prints_block = "\n".join(top_prints) if top_prints else "  • No major institutional whale prints recorded."

    return f"""You are Quant AI's institutional Options Microstructure & Unusual Flow Market Strategist.
Analyze the following real-time options microstructure and institutional order flow data for {ticker}:

[OPTIONS MICROSTRUCTURE (GEX/DEX)]
• Spot Price: ${metrics.get('spot_price', 0.0):.2f}
• Zero Gamma Flip: ${metrics.get('zero_gamma_flip', 0.0):.2f}
• Call Wall (Major Resistance): ${metrics.get('call_wall', 0.0):.2f}
• Put Wall (Major Support): ${metrics.get('put_wall', 0.0):.2f}
• Net GEX: ${metrics.get('net_gex', 0.0):,.2f}
• Net DEX: ${metrics.get('net_dex', 0.0):,.2f}
• Gamma Regime: {metrics.get('gamma_regime', 'N/A')}
• Expected 1-Week Range: ${gex.get('expected_range_low', 'N/A')} to ${gex.get('expected_range_high', 'N/A')} (Expected Move: ${gex.get('expected_move_dollars', 'N/A')})

[30-DAY INSTITUTIONAL OPTIONS FLOW]
• Total Flow Volume: ${metrics.get('total_30d_flow_volume', 0.0):,.2f}
• Call Flow: ${metrics.get('call_flow', 0.0):,.2f} ({metrics.get('call_pct', 0.0):.1f}%) | Put Flow: ${metrics.get('put_flow', 0.0):,.2f} ({metrics.get('put_pct', 0.0):.1f}%)
• Whale Sweeps (> $1M): {metrics.get('whale_count', 0)} prints
• Unusual OI Alerts: {metrics.get('unusual_oi_count', 0)}
• Calculated Confluence Bias: {metrics.get('confluence_bias', 'NEUTRAL PIN')}

[HIGH-CONVICTION PRINTS]
{prints_block}

Demand format: Deliver the institutional 3-Tier Tactical Playbook in crisp GitHub Markdown:

### 1. Core Confluence Thesis
Synthesize the interaction between the Gamma Regime ({metrics.get('gamma_regime')}) and 30-day directional flow sentiment ({metrics.get('confluence_bias')}). Explain market maker inventory obligations (long vs short gamma) and whether volatility is dampened or amplified.

### 2. Microstructure Alignment
Evaluate institutional order flow (whale sweeps and unusual OI) relative to structural volatility landmarks (Call Wall at ${metrics.get('call_wall')}, Put Wall at ${metrics.get('put_wall')}, and Zero Gamma Flip at ${metrics.get('zero_gamma_flip')}). Highlight pin risk, squeeze potential, or cascade vulnerability.

### 3. Tactical Action Playbook
Provide concrete institutional execution parameters:
- **Key Triggers & Levels**: Specific breakout and breakdown trigger prices.
- **Pin vs Breakout Scenarios**: Target price zones if pinned vs expansion targets if outer walls breach.
- **Trade Invalidation**: Exact price level where this confluence thesis is invalidated.
"""


def _generate_deterministic_synthesis(ticker: str, payload: Dict[str, Any]) -> str:
    """Fallback deterministic synthesis generator when Gemini API is offline or unconfigured."""
    metrics = payload.get("metrics", {})
    spot = metrics.get("spot_price", 0.0)
    cw = metrics.get("call_wall", 0.0)
    pw = metrics.get("put_wall", 0.0)
    zg = metrics.get("zero_gamma_flip", 0.0)
    regime = metrics.get("gamma_regime", "Positive Gamma")
    bias = metrics.get("confluence_bias", "NEUTRAL PIN")
    call_pct = metrics.get("call_pct", 0.0)
    put_pct = metrics.get("put_pct", 0.0)
    vol = metrics.get("total_30d_flow_volume", 0.0)
    whales = metrics.get("whale_count", 0)
    unusual_oi = metrics.get("unusual_oi_count", 0)

    return f"""### 1. Core Confluence Thesis
- **Gamma Regime**: {regime}. Spot price (${spot:.2f}) trades relative to the Zero Gamma Flip level at ${zg:.2f}.
- **Flow Momentum**: 30-Day institutional volume stands at ${vol:,.2f} with {call_pct:.1f}% Call flow vs {put_pct:.1f}% Put flow, establishing a **{bias}** setup.
- **Dealer Inventory**: Market maker hedging profiles indicate structured positioning across dominant expirations.

### 2. Microstructure Alignment
- **Call Wall Resistance**: ${cw:.2f} marks upper dealer gamma supply and key upside resistance.
- **Put Wall Support**: ${pw:.2f} provides downside dealer gamma insulation.
- **Institutional Conviction**: {whales} whale prints (> $1M) and {unusual_oi} unusual OI flags align with current volatility corridors.

### 3. Tactical Action Playbook
- **Key Triggers & Levels**: Upward breakout trigger above ${cw:.2f}; downside volatility trigger below ${zg:.2f} targeting ${pw:.2f}.
- **Pin vs Breakout Scenarios**: High probability of range pinning between ${pw:.2f} and ${cw:.2f} into dominant expiration.
- **Trade Invalidation**: Thesis invalidates on a sustained daily candle close outside the ${pw:.2f} – ${cw:.2f} range.
"""


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
    return await _stream_synthesis_impl(request, clean_ticker)


async def _stream_synthesis_impl(request: Request, clean_ticker: str):
    # 1. Fetch cockpit data payload
    cockpit_payload = await get_cockpit_full_payload(clean_ticker)
    prompt = _build_synthesis_prompt(clean_ticker, cockpit_payload)

    async def sse_generator():
        try:
            if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip():
                try:
                    from google import genai
                    from google.genai import types

                    client = genai.Client(
                        api_key=settings.GEMINI_API_KEY,
                        http_options=types.HttpOptions(timeout=60000, retry_options=types.HttpRetryOptions(attempts=1))
                    )

                    model_name = settings.TIER1_FAST_WORKER_MODEL or "gemini-3.5-flash-lite"
                    gen_config = types.GenerateContentConfig(
                        temperature=0.2,
                        system_instruction="You are Quant AI, an elite institutional options microstructure strategist."
                    )

                    response_stream = await client.aio.models.generate_content_stream(
                        model=model_name,
                        contents=prompt,
                        config=gen_config
                    )

                    async for chunk in response_stream:
                        if await request.is_disconnected():
                            logger.info(f"Client disconnected during synthesis stream for {clean_ticker}")
                            return
                        if chunk.text:
                            payload_json = json.dumps({"type": "token", "content": chunk.text})
                            yield f"data: {payload_json}\n\n"

                    yield "data: [DONE]\n\n"
                    return
                except Exception as genai_err:
                    logger.warning(f"Gemini API streaming error for {clean_ticker}: {genai_err}. Falling back to deterministic synthesis.")

            # Fallback deterministic synthesis stream
            fallback_text = _generate_deterministic_synthesis(clean_ticker, cockpit_payload)
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
