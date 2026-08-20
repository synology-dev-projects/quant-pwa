import json
import httpx
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
    record_successful_attempt
)

app = FastAPI(
    title="Quant AI Agent Gateway",
    description="Ultra-low latency BFF Gateway for Quant AI Mobile Chat PWA on Synology NAS.",
    version="1.0.0"
)

# Enable CORS for PWA and Cloudflare tunnel origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_app_passcode(authorization: Optional[str] = Header(None)) -> str:
    """
    Validates Authorization Bearer token header.
    Accepts valid HMAC-SHA256 session tokens (within 6h expiration)
    or direct APP_PASSCODE matching (fallback).
    """
    if not settings.APP_PASSCODE:
        return "open"
        
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

    # 2. Check direct master password match (fallback for scripts / tooling)
    if validate_master_password(token):
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
        "auth_required": bool(settings.APP_PASSCODE),
        "session_expiry_hours": settings.SESSION_EXPIRY_HOURS
    }


@app.post("/api/auth/login", summary="Login and Generate 6-Hour Session Token")
async def auth_login(req: LoginRequest, request: Request):
    """
    Validates master password and generates a signed 6-hour HMAC-SHA256 session token.
    Enforces IP-based rate limiting (5 attempts per 5 minutes) and 15-minute brute-force lockout.
    """
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
def health_check():
    """Health check endpoint for Docker container orchestration and Synology NAS monitoring."""
    market_meta = get_market_status()
    return {
        "status": "ok",
        "service": "quant-gateway",
        "market": market_meta
    }


@app.get("/api/models", summary="List Available Gemini Models", dependencies=[Depends(verify_app_passcode)])
def list_models():
    """Returns available Gemini models for the PWA header dropdown."""
    return {
        "default": "gemini-3.5-flash",
        "models": [
            {"id": "gemini-3.5-flash", "name": "Gemini 3.5 Flash", "badge": "Fast + Zero Congestion (Default)"},
            {"id": "gemini-3.7-flash", "name": "Gemini 3.7 Flash", "badge": "High Accuracy Preview"},
            {"id": "gemini-3-flash-preview", "name": "Gemini 3 Flash Preview", "badge": "Ultra Low Latency"},
            {"id": "gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash Lite", "badge": "Cost Efficient"}
        ]
    }


@app.get("/api/v1/gexdex/chart.png", summary="Proxy GEX/DEX Chart WebP/PNG")
def proxy_chart_png(
    ticker: str = Query("AAPL"),
    max_dte: int = Query(50),
    strike_range: int = Query(25),
    t: Optional[str] = Query(None),
    format: str = Query("webp"),
    force_refresh: bool = Query(False),
    api_key: Optional[str] = None
):
    """
    Proxies chart image requests directly to the internal gexdex-api microservice.
    Enforces WebP compression (~35KB), strict Cache-Control headers, and force_refresh support.
    """
    clean_ticker = ticker.strip().upper()
    url = f"{settings.GEXDEX_API_URL}/api/v1/gexdex/chart.png"
    params = {
        "ticker": clean_ticker,
        "max_dte": max_dte,
        "strike_range": strike_range,
        "format": format,
        "force_refresh": str(force_refresh).lower()
    }
    headers = {
        "X-API-Key": settings.GEXDEX_API_KEY
    }
    cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params, headers=headers)
            media_type = "image/webp" if format.lower() == "webp" else "image/png"
            return Response(
                content=resp.content,
                media_type=media_type,
                status_code=resp.status_code,
                headers=cache_headers
            )
    except Exception as e:
        return Response(content=b"", media_type="image/png", status_code=502, headers=cache_headers)


@app.get("/api/v1/gexdex/strikes", summary="Proxy GEX/DEX Strike Distribution JSON", dependencies=[Depends(verify_app_passcode)])
def proxy_strikes(
    ticker: str = Query("AAPL"),
    max_dte: int = Query(50),
    strike_range: int = Query(25),
    force_refresh: bool = Query(False)
):
    """
    Proxies strike distribution JSON directly to gexdex-api.
    Used for on-demand chart rehydration and standalone queries.
    """
    clean_ticker = ticker.strip().upper()
    url = f"{settings.GEXDEX_API_URL}/api/v1/gexdex/strikes"
    params = {
        "ticker": clean_ticker,
        "max_dte": max_dte,
        "strike_range": strike_range,
        "force_refresh": str(force_refresh).lower()
    }
    headers = {
        "X-API-Key": settings.GEXDEX_API_KEY
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params, headers=headers)
            return Response(
                content=resp.content,
                media_type="application/json",
                status_code=resp.status_code
            )
    except Exception as e:
        return {"error": f"Failed to reach gexdex-api: {str(e)}", "ticker": clean_ticker}


@app.post("/api/chat/stream", summary="Stream Chat Response", dependencies=[Depends(verify_app_passcode)])
async def chat_stream(request: Request, body: ChatStreamRequest):
    """
    Streams AI responses with low-latency Server-Sent Events (SSE).
    Monitors request.is_disconnected() to cancel upstream processing if mobile client drops.
    """
    message_dicts = [{"role": m.role, "content": m.content} for m in body.messages]
    
    async def sse_generator():
        async for chunk in stream_chat_response(
            messages=message_dicts,
            model_name=body.model,
            client_disconnected_fn=request.is_disconnected
        ):
            yield chunk

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
