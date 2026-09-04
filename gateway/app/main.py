import json
import httpx
import asyncio
import logging
import secrets
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Request, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from app.config import settings
from app.core.agent import stream_chat_response
from app.core.temporal import get_market_status
from app.core.auth import (
    create_session_token,
    verify_session_token,
    validate_master_password,
    check_rate_limit,
    record_failed_attempt,
    record_successful_attempt,
    verify_app_passcode,
    get_current_user
)

from contextlib import asynccontextmanager
from app.mcp import mcp_router, mcp_client_manager, mcp_sse_endpoint, mcp_post_message
from app.routers.cockpit import router as cockpit_router
from app.routers.flow_status import router as flow_status_router
from app.routers.quant_levels_status import router as quant_levels_status_router
from app.routers.scanner import router as scanner_router
from app.tools.gexdex_tool import run_cache_warmer_loop
from app.engine.service import gexdex_service

import collections
from collections import deque

_RECENT_LOG_BUFFER = deque(maxlen=200)

class _RingBufferHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            _RECENT_LOG_BUFFER.append(msg)
        except Exception:
            pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("quant.gateway")
_rb_handler = _RingBufferHandler()
_rb_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(_rb_handler)
# Also capture root logger for full framework events
logging.getLogger().addHandler(_rb_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Auto-migrate & verify canonical database schemas
    try:
        from common_lib.database.schemas import ensure_all_schemas
        ensure_all_schemas()
    except Exception as e:
        logger.warning(f"Schema verification skipped or failed on startup: {e}")

    # Startup: Initialize MCP Client Hub
    await mcp_client_manager.initialize()
    # Startup: Background Market Hours Pre-Cache Warmer (In-Process Engine)
    warmer_task = asyncio.create_task(run_cache_warmer_loop())
    yield
    # Shutdown: Cancel pre-cache warmer gracefully
    warmer_task.cancel()
    try:
        await warmer_task
    except asyncio.CancelledError:
        pass
    # Shutdown: Close active MCP sessions
    await mcp_client_manager.close()


app = FastAPI(
    title="Quant AI Agent Gateway",
    description="Ultra-low latency BFF Gateway with bi-directional Model Context Protocol (MCP) support for Quant AI Mobile Chat PWA on Synology NAS.",
    version="1.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID") or f"tr-{secrets.token_hex(3)}"
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response

# Enable CORS for PWA and Cloudflare tunnel origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Model Context Protocol (MCP) Router
app.include_router(mcp_router)

# Root aliases for MCP endpoints
app.add_api_route("/sse", mcp_sse_endpoint, methods=["GET", "POST"], tags=["MCP Server"], include_in_schema=False)
app.add_api_route("/messages", mcp_post_message, methods=["GET", "POST"], tags=["MCP Server"], include_in_schema=False)

# Mount Ticker Cockpit Router (Protected by 6-Hour Session Token Auth)
app.include_router(
    cockpit_router,
    prefix="/api/cockpit",
    dependencies=[Depends(get_current_user)]
)

# Mount Options Flow Ingestion Status Router
app.include_router(
    flow_status_router,
    prefix="/api/flow"
)

# Mount Quant Levels Ingestion Status Router
app.include_router(
    quant_levels_status_router,
    prefix="/api/quant-levels"
)

# Mount Market Confluence Scanner Router
app.include_router(scanner_router)



def verify_app_passcode(authorization: Optional[str] = Header(None)) -> str:
    """
    Validates Authorization Bearer token header.
    Accepts valid HMAC-SHA256 session tokens (within 6h expiration)
    or direct APP_PASSCODE matching (fallback).
    Enforces fail-closed passcode validation.
    """
    if not settings.APP_PASSCODE or not settings.APP_PASSCODE.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server passcode unconfigured.",
        )
        
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization Bearer header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.split("Bearer ")[1].strip()
    
    # 1. Check if token is a valid signed session token
    session_payload = verify_session_token(token)
    if session_payload is not None:
        return session_payload.get("sub", "quant-user")

    # 2. Check direct master password match using constant-time comparison (fallback for scripts / tooling)
    if secrets.compare_digest(token, settings.APP_PASSCODE.strip()) or validate_master_password(token):
        return "quant-master"
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expired or invalid passcode. Please unlock the app again.",
        headers={"WWW-Authenticate": "Bearer"},
    )


class LoginRequest(BaseModel):
    password: str

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatStreamRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None


@app.get("/api/auth/status", summary="Authentication Gate Status")
def auth_status():
    """Returns authentication gate requirements and session lifetime."""
    return {
        "auth_required": bool(settings.APP_PASSCODE and settings.APP_PASSCODE.strip()),
        "session_expiry_hours": settings.SESSION_EXPIRY_HOURS
    }


@app.post("/api/auth/login", summary="Login and Generate 6-Hour Session Token")
async def auth_login(req: LoginRequest, request: Request):
    """
    Validates master password and generates a signed 6-hour HMAC-SHA256 session token.
    Enforces IP-based rate limiting (5 attempts per 5 minutes) and 15-minute brute-force lockout.
    """
    if not settings.APP_PASSCODE or not settings.APP_PASSCODE.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server passcode unconfigured."
        )
    # Extract client IP (handling reverse proxies & Cloudflare headers)
    client_ip = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-real-ip")
        or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )

    # 1. Check if IP is currently locked out
    is_allowed, lockout_remaining = check_rate_limit(client_ip)
    if not is_allowed:
        minutes_remaining = max(1, int(lockout_remaining / 60))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Account locked for security. Please try again in {minutes_remaining} minutes.",
            headers={"Retry-After": str(lockout_remaining)}
        )

    # 2. Validate password
    if not validate_master_password(req.password):
        # Tarpitting delay (500ms) to throttle automated attacks
        import asyncio
        await asyncio.sleep(0.5)

        attempts_left, is_locked, lock_secs = record_failed_attempt(client_ip)
        if is_locked:
            minutes = int(lock_secs / 60)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts. Locked out for {minutes} minutes.",
                headers={"Retry-After": str(lock_secs)}
            )
        
        attempt_msg = f"{attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining before lockout."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid passcode. {attempt_msg}"
        )
    
    # 3. Successful login - clear failed attempts & issue 6h token
    record_successful_attempt(client_ip)
    token, expires_at = create_session_token(expires_in_hours=settings.SESSION_EXPIRY_HOURS)
    return {
        "token": token,
        "expires_at": expires_at,
        "expires_in_hours": settings.SESSION_EXPIRY_HOURS,
        "message": "Authenticated successfully."
    }


@app.get("/api/auth/verify", summary="Verify Active Session Token")
def auth_verify(user: str = Depends(verify_app_passcode)):
    """Verifies that the current Authorization header contains a valid active session."""
    return {
        "valid": True,
        "user": user
    }


@app.get("/health", summary="Health Check")
@app.get("/api/health", summary="Health Check API Alias")
def health_check():
    """Health check endpoint for Docker container orchestration and Synology NAS monitoring."""
    market_meta = get_market_status()
    return {
        "status": "ok",
        "service": "quant-gateway",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "market": market_meta
    }


@app.get("/api/models", summary="List Available Gemini Models", dependencies=[Depends(verify_app_passcode)])
def list_models():
    """Returns available Gemini models for the PWA header dropdown."""
    return {
        "default": settings.DEFAULT_GEMINI_MODEL,
        "models": settings.AVAILABLE_MODELS
    }


@app.get("/api/v1/gexdex/assistant-summary", summary="Get Options Exposure Summary for AI Assistants")
async def get_gexdex_assistant_summary(
    tickers: Optional[str] = Query(None, description="Single ticker or comma-separated list (e.g. AAPL,INTC,SPY)"),
    ticker: Optional[str] = Query(None, description="Legacy single ticker parameter"),
    max_dte: int = Query(50, description="Maximum days to expiration (default: 50)"),
    strike_range: int = Query(25, description="Strike range above/below spot price (default: 25)"),
    force_refresh: bool = Query(False, description="Bypass cache and force live data fetch")
):
    """
    In-process GEX/DEX options calculation engine summary route.
    Fetches real-time GEX/DEX options exposure metrics for single or multiple tickers.
    """
    raw_param = tickers or ticker or "AAPL"
    result = await gexdex_service.get_summary(
        ticker=raw_param,
        max_dte=max_dte,
        strike_range=strike_range,
        force_refresh=force_refresh
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No options exposure data found for tickers: {raw_param}"
        )
    return result


@app.get("/api/v1/gexdex/chart.png", summary="GEX/DEX Chart WebP/PNG")
async def get_chart_png(
    ticker: str = Query("AAPL"),
    max_dte: int = Query(50),
    strike_range: int = Query(25),
    t: Optional[str] = Query(None),
    format: str = Query("webp"),
    force_refresh: bool = Query(False),
    api_key: Optional[str] = None
):
    """
    Generates GEX/DEX chart image directly in-process via GexDexService.
    Enforces WebP compression (~35KB), strict Cache-Control headers, and force_refresh support.
    """
    clean_ticker = ticker.strip().upper()
    img_fmt = format.lower() if format else "webp"
    img_bytes = await gexdex_service.get_chart_image(
        ticker=clean_ticker,
        format=img_fmt,
        max_dte=max_dte,
        strike_range=strike_range,
        force_refresh=force_refresh
    )
    media_type = "image/webp" if img_fmt == "webp" else "image/png"
    cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return Response(
        content=img_bytes,
        media_type=media_type,
        status_code=200 if img_bytes else 502,
        headers=cache_headers
    )


@app.get("/api/v1/gexdex/strikes", summary="GEX/DEX Strike Distribution JSON", dependencies=[Depends(verify_app_passcode)])
async def get_strikes_json(
    ticker: str = Query("AAPL"),
    max_dte: int = Query(50),
    strike_range: int = Query(25),
    force_refresh: bool = Query(False)
):
    """
    Retrieves granular strike distribution JSON directly in-process.
    Used for on-demand chart rehydration and standalone queries.
    """
    clean_ticker = ticker.strip().upper()
    return await gexdex_service.get_strikes(
        ticker=clean_ticker,
        max_dte=max_dte,
        strike_range=strike_range,
        force_refresh=force_refresh
    )


@app.post("/api/chat/stream", summary="Stream Chat Response", dependencies=[Depends(verify_app_passcode)])
async def chat_stream(request: Request, body: ChatStreamRequest):
    """
    Streams AI responses with low-latency Server-Sent Events (SSE).
    Monitors request.is_disconnected() to cancel upstream processing if mobile client drops.
    Enforces fail-closed passcode validation and structured trace correlation.
    """
    if not settings.APP_PASSCODE or not settings.APP_PASSCODE.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server passcode unconfigured."
        )

    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-ID") or f"tr-{secrets.token_hex(3)}"
    logger.info(f"[{trace_id}] Received chat stream request: model={body.model}, messages_count={len(body.messages)}")

    message_dicts = [{"role": m.role, "content": m.content} for m in body.messages]
    
    async def sse_generator():
        try:
            async for chunk in stream_chat_response(
                messages=message_dicts,
                model_name=body.model,
                client_disconnected_fn=request.is_disconnected,
                trace_id=trace_id
            ):
                yield chunk
            logger.info(f"[{trace_id}] Chat stream completed successfully.")
        except Exception as e:
            logger.error(f"[{trace_id}] Chat stream exception: {str(e)}")
            raise

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Trace-ID": trace_id
        }
    )


@app.get("/api/diagnostics/logs", summary="Get Recent Server Logs", dependencies=[Depends(verify_app_passcode)])
async def get_recent_logs(limit: int = Query(default=100, ge=1, le=200)):
    """Returns recent in-memory server log lines for debugging and trace analysis."""
    logs = list(_RECENT_LOG_BUFFER)
    return {"total": len(logs), "logs": logs[-limit:]}
