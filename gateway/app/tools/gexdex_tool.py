import time
import httpx
from typing import Dict, Any, Optional
from app.config import settings
from app.tools.registry import register_tool, emit_tool_ui_event

@register_tool(
    name="get_gexdex",
    description="Fetch proprietary institutional options Gamma Exposure (GEX) and Delta Exposure (DEX) analytics for one or more stock ticker symbols (e.g. AAPL, TSLA, NVDA, SPY, QQQ). Accepts single tickers or comma-separated ticker lists. Returns spot price, net GEX/DEX, zero gamma flip level, key call/put walls, and authenticated chart image URLs.",
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol or comma-separated list (e.g. AAPL or AAPL,TSLA,SPY)"
            },
            "tickers": {
                "type": "string",
                "description": "Optional comma-separated list of stock ticker symbols"
            },
            "max_dte": {
                "type": "integer",
                "description": "Maximum days to expiration to include in the options calculation (default: 50)"
            },
            "strike_range": {
                "type": "integer",
                "description": "Number of strikes above/below the current spot price to evaluate (default: 25)"
            },
            "force_refresh": {
                "type": "boolean",
                "description": "Force live fetch bypassing 1-hour cache (default: False)"
            }
        },
        "required": ["ticker"]
    }
)
def get_gexdex(
    ticker: str = "",
    max_dte: int = 50,
    strike_range: int = 25,
    force_refresh: bool = False,
    tickers: Optional[str] = None
) -> Dict[str, Any]:
    """
    Queries gexdex-api assistant-summary endpoint over the internal Synology LAN.
    Supports single or batch tickers and force_refresh on demand.
    """
    raw_input = tickers or ticker
    if isinstance(raw_input, list):
        clean_tickers = ",".join([t.strip().upper().replace("$", "") for t in raw_input if t.strip()])
    else:
        clean_tickers = ",".join([t.strip().upper().replace("$", "") for t in str(raw_input).split(",") if t.strip()])

    url = f"{settings.GEXDEX_API_URL}/api/v1/gexdex/assistant-summary"
    params = {
        "tickers": clean_tickers,
        "max_dte": max_dte,
        "strike_range": strike_range,
        "force_refresh": str(force_refresh).lower()
    }
    headers = {
        "X-API-Key": settings.GEXDEX_API_KEY
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                base_url = settings.PUBLIC_BASE_URL.rstrip("/") if settings.PUBLIC_BASE_URL else ""
                timestamp = int(time.time())
                refresh_query = "&force_refresh=true" if force_refresh else ""

                # Handle batch response
                if "batch_data" in data and isinstance(data["batch_data"], dict):
                    for sym, item in data["batch_data"].items():
                        # Emit Single-Flight Tool UI event for client-side Canvas rendering
                        if "strike_distribution" in item and item["strike_distribution"]:
                            emit_tool_ui_event("get_gexdex", item["strike_distribution"])
                        # Strip static image fields so LLM does not output redundant markdown images
                        item.pop("markdown_image", None)
                        item.pop("chart_png_url", None)
                else:
                    if "strike_distribution" in data and data["strike_distribution"]:
                        emit_tool_ui_event("get_gexdex", data["strike_distribution"])
                
                # Strip root-level static image fields
                data.pop("markdown_image", None)
                data.pop("chart_png_url", None)
                
                return data
            else:
                return {
                    "error": f"gexdex-api returned HTTP {response.status_code}",
                    "detail": response.text,
                    "ticker": clean_tickers
                }
    except httpx.ConnectError:
        return {
            "error": "Failed to connect to gexdex-api microservice on Synology NAS.",
            "detail": f"Could not reach {settings.GEXDEX_API_URL}. Ensure container is running.",
            "ticker": clean_tickers
        }
    except Exception as e:
        return {
            "error": f"Unexpected error querying gexdex-api: {str(e)}",
            "ticker": clean_tickers
        }
