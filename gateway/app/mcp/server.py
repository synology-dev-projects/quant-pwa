"""
FAANG-Grade Model Context Protocol (MCP) SSE Server for Quant AI Agent Gateway.
Compliant with MCP Protocol Version 2024-11-05.

Exposes institutional tools, resources, and prompt templates to external MCP clients:
- Tools: get_gexdex, get_strike_distribution, get_market_status, list_models
- Resources: quant://market-status, quant://gexdex/{ticker}
- Prompts: options-dealer-analysis, macro-catalyst-check
"""

import json
import uuid
import inspect
import asyncio
import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Request, HTTPException, Depends, status, Query
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.core.temporal import get_market_status
from app.tools.gexdex_tool import get_gexdex, get_strike_distribution
from app.tools.flow_tool import get_unusual_flow

logger = logging.getLogger("quant.mcp.server")

router = APIRouter(prefix="/mcp", tags=["MCP Server"])

# Active MCP SSE client sessions: session_id -> asyncio.Queue
_active_sessions: Dict[str, asyncio.Queue] = {}

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "quant-ai-gateway",
    "version": "1.0.0"
}

MCP_TOOLS = [
    {
        "name": "get_gexdex",
        "description": "Calculates institutional Gamma Exposure (GEX), Delta Exposure (DEX), Call/Put Walls, and Zero Gamma Flips for one or multiple stock tickers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Single ticker or comma-separated list of stock tickers (e.g. SPY, AAPL, NVDA, TSLA)."
                },
                "strike_range": {
                    "type": "integer",
                    "description": "Number of strikes above and below spot to calculate.",
                    "default": 25
                },
                "max_dte": {
                    "type": "integer",
                    "description": "Maximum days to expiration to include.",
                    "default": 50
                }
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_strike_distribution",
        "description": "Fetches granular strike-by-strike GEX and DEX distribution with multi-expiration breakdowns for interactive charting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Single stock ticker (e.g. NVDA, SPY)."
                },
                "strike_range": {
                    "type": "integer",
                    "description": "Number of strikes above and below spot.",
                    "default": 25
                },
                "max_dte": {
                    "type": "integer",
                    "description": "Maximum DTE.",
                    "default": 50
                }
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_market_status",
        "description": "Returns current US Equity and Options market session status, trading hours, and time to open/close.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_unusual_flow",
        "description": "Retrieves 100% complete institutional unusual options flow prints as a pure-data Bloomberg table. Accepts an optional date parameter (e.g. '2026-08-21', 'Friday', 'yesterday', '2026-08-17 to 2026-08-21', 'latest').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Optional market session date, range, or keyword (e.g. '2026-08-21', 'Friday', 'yesterday', '2026-08-17 to 2026-08-21', 'latest'). Defaults to latest session if omitted."
                },
                "ticker": {
                    "type": "string",
                    "description": "Optional ticker symbol (e.g. 'NVDA') or date string if passed positionally."
                },
                "min_premium": {
                    "type": "number",
                    "description": "Minimum trade premium in USD.",
                    "default": 0.0
                }
            }
        }
    }
]

MCP_RESOURCES = [
    {
        "uri": "quant://market-status",
        "name": "Live US Market Status",
        "description": "Real-time market session status, current market time, and session countdown.",
        "mimeType": "application/json"
    },
    {
        "uri": "quant://gexdex/SPY",
        "name": "SPY GEX/DEX Summary",
        "description": "Current institutional dealer positioning for SPY ETF.",
        "mimeType": "application/json"
    }
]

MCP_PROMPTS = [
    {
        "name": "options-dealer-analysis",
        "description": "Executes a deep institutional dealer gamma regime analysis on target tickers.",
        "arguments": [
            {
                "name": "tickers",
                "description": "Comma-separated list of symbols (e.g. SPY, QQQ, NVDA)",
                "required": True
            }
        ]
    }
]


async def handle_rpc_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Processes a JSON-RPC 2.0 request compliant with MCP 2024-11-05 specification."""
    req_id = request_data.get("id")
    method = request_data.get("method")
    params = request_data.get("params", {})

    if not method:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32600, "message": "Invalid Request: method is required"}
        }

    try:
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False}
                    },
                    "serverInfo": SERVER_INFO
                }
            }

        elif method == "notifications/initialized":
            return None

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": MCP_TOOLS}
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})

            if tool_name == "get_gexdex":
                ticker = args.get("ticker", "SPY")
                strike_range = int(args.get("strike_range", 25))
                max_dte = int(args.get("max_dte", 50))
                res = get_gexdex(ticker=ticker, strike_range=strike_range, max_dte=max_dte)
                if inspect.isawaitable(res):
                    res = await res
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": res if isinstance(res, str) else json.dumps(res, indent=2)}
                        ],
                        "isError": False
                    }
                }

            elif tool_name == "get_strike_distribution":
                ticker = args.get("ticker", "SPY")
                strike_range = int(args.get("strike_range", 25))
                max_dte = int(args.get("max_dte", 50))
                res = get_strike_distribution(ticker=ticker, strike_range=strike_range, max_dte=max_dte)
                if inspect.isawaitable(res):
                    res = await res
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(res, indent=2)}
                        ],
                        "isError": False
                    }
                }

            elif tool_name == "get_market_status":
                status_res = get_market_status()
                if inspect.isawaitable(status_res):
                    status_res = await status_res
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(status_res, indent=2)}
                        ],
                        "isError": False
                    }
                }

            elif tool_name == "get_unusual_flow":
                date_val = args.get("date") or args.get("trade_date")
                ticker_val = args.get("ticker")
                min_prem = float(args.get("min_premium", 0.0))
                res = get_unusual_flow(date=date_val, ticker=ticker_val, min_premium=min_prem)
                if inspect.isawaitable(res):
                    res = await res
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": res if isinstance(res, str) else json.dumps(res, indent=2)}
                        ],
                        "isError": False
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}
                }

        elif method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"resources": MCP_RESOURCES}
            }

        elif method == "resources/read":
            uri = params.get("uri", "")
            if uri == "quant://market-status":
                status_res = get_market_status()
                if inspect.isawaitable(status_res):
                    status_res = await status_res
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(status_res, indent=2)
                            }
                        ]
                    }
                }
            elif uri.startswith("quant://gexdex/"):
                ticker = uri.replace("quant://gexdex/", "").strip().upper()
                res = get_gexdex(ticker=ticker)
                if inspect.isawaitable(res):
                    res = await res
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "text/plain" if isinstance(res, str) else "application/json",
                                "text": res if isinstance(res, str) else json.dumps(res, indent=2)
                            }
                        ]
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32002, "message": f"Resource not found: {uri}"}
                }

        elif method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"prompts": MCP_PROMPTS}
            }

        elif method == "prompts/get":
            prompt_name = params.get("name")
            args = params.get("arguments", {})
            if prompt_name == "options-dealer-analysis":
                tickers = args.get("tickers", "SPY, QQQ, NVDA")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "description": "Deep institutional dealer gamma regime analysis",
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": f"Please perform a complete quantitative dealer positioning and GEX/DEX analysis for the following symbols: {tickers}. Identify Call/Put walls, Gamma Flip points, and rank their volatility profiles."
                                }
                            }
                        ]
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Prompt not found: {prompt_name}"}
                }

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not implemented: {method}"}
            }

    except Exception as e:
        logger.error(f"Error handling MCP method {method}: {e}", exc_info=True)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }


@router.get("/sse", summary="MCP Server-Sent Events Transport")
async def mcp_sse_endpoint(request: Request):
    """
    MCP 2024-11-05 SSE Transport Endpoint.
    Initiates SSE stream and returns the endpoint URI for posting JSON-RPC messages.
    """
    session_id = str(uuid.uuid4())
    queue = asyncio.Queue()
    _active_sessions[session_id] = queue

    logger.info(f"New MCP SSE client connected. session_id={session_id}")

    async def event_generator():
        # First event: announce message POST endpoint
        endpoint_event = f"event: endpoint\ndata: /mcp/messages?session_id={session_id}\n\n"
        yield endpoint_event

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait for outgoing message to client
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive comment
                    yield ": keep-alive\n\n"
        finally:
            _active_sessions.pop(session_id, None)
            logger.info(f"MCP SSE client disconnected. session_id={session_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/messages", summary="MCP JSON-RPC Message Transport")
async def mcp_post_message(
    request: Request,
    session_id: Optional[str] = Query(None)
):
    """
    Receives JSON-RPC messages from MCP clients.
    Dispatches request and pushes the response either to the client's SSE stream or directly as JSON.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    response_payload = await handle_rpc_request(body)

    if session_id and session_id in _active_sessions:
        if response_payload:
            await _active_sessions[session_id].put(response_payload)
        return JSONResponse(content={"status": "accepted"}, status_code=202)

    # If no active SSE session_id specified, return direct HTTP response
    if response_payload:
        return JSONResponse(content=response_payload, status_code=200)
    return JSONResponse(content={"status": "ok"}, status_code=200)
