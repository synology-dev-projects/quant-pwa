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
    Validates Authorization Bearer passcode header against APP_PASSCODE.
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
    if token != settings.APP_PASSCODE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid App Passcode. Update passcode in PWA Settings.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


class ChatMessage(BaseModel):
    role: str
    content: str

class ChatStreamRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None


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
        "default": settings.DEFAULT_GEMINI_MODEL,
        "models": [
            {"id": "gemini-3.7-flash", "name": "Gemini 3.7 Flash", "badge": "Fast + High Accuracy (Default)"},
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "badge": "High Availability (No 503s)"},
            {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "badge": "Deep Chain-of-Thought Reasoning"},
            {"id": "gemini-flash-latest", "name": "Gemini Flash Latest", "badge": "Production Flash"}
        ]
    }


@app.get("/api/v1/gexdex/chart.png", summary="Proxy GEX/DEX Chart PNG")
def proxy_chart_png(
    ticker: str = Query("AAPL"),
    max_dte: int = Query(50),
    strike_range: int = Query(25),
    t: Optional[str] = Query(None),
    api_key: Optional[str] = None
):
    """
    Proxies chart PNG requests directly to the internal gexdex-api microservice.
    Enforces strict Cache-Control headers so browsers never display stale cached charts.
    """
    clean_ticker = ticker.strip().upper()
    url = f"{settings.GEXDEX_API_URL}/api/v1/gexdex/chart.png"
    params = {
        "ticker": clean_ticker,
        "max_dte": max_dte,
        "strike_range": strike_range,
        "format": "png"
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
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params, headers=headers)
            return Response(
                content=resp.content,
                media_type="image/png",
                status_code=resp.status_code,
                headers=cache_headers
            )
    except Exception as e:
        return Response(content=b"", media_type="image/png", status_code=502, headers=cache_headers)


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
