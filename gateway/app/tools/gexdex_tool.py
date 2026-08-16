import time
import httpx
from typing import Dict, Any
from app.config import settings
from app.tools.registry import register_tool

@register_tool(
    name="get_gexdex",
    description="Fetch proprietary institutional options Gamma Exposure (GEX) and Delta Exposure (DEX) analytics for a stock ticker symbol (e.g. AAPL, TSLA, NVDA, SPY, QQQ). Returns spot price, net GEX/DEX, zero gamma flip level, key call/put walls, and an authenticated chart image URL.",
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g. AAPL, TSLA, NVDA, SPY, QQQ)"
            },
            "max_dte": {
                "type": "integer",
                "description": "Maximum days to expiration to include in the options calculation (default: 50)"
            },
            "strike_range": {
                "type": "integer",
                "description": "Number of strikes above/below the current spot price to evaluate (default: 25)"
            }
        },
        "required": ["ticker"]
    }
)
def get_gexdex(ticker: str, max_dte: int = 50, strike_range: int = 25) -> Dict[str, Any]:
    """
    Queries gexdex-api assistant-summary endpoint over the internal Synology LAN.
    Uses synchronous httpx.Client for compatibility with GenAI automatic function calling.
    """
    clean_ticker = ticker.strip().upper().replace("$", "")
    url = f"{settings.GEXDEX_API_URL}/api/v1/gexdex/assistant-summary"
    params = {
        "ticker": clean_ticker,
        "max_dte": max_dte,
        "strike_range": strike_range
    }
    headers = {
        "X-API-Key": settings.GEXDEX_API_KEY
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Build client-accessible authenticated cache-busted chart URL
                base_url = settings.PUBLIC_BASE_URL.rstrip("/") if settings.PUBLIC_BASE_URL else ""
                timestamp = int(time.time())
                auth_chart_url = f"{base_url}/api/v1/gexdex/chart.png?ticker={clean_ticker}&max_dte={max_dte}&strike_range={strike_range}&t={timestamp}"
                
                data["chart_png_url"] = auth_chart_url
                data["markdown_image"] = f"![{clean_ticker} Options Chart]({auth_chart_url})"
                return data
            else:
                return {
                    "error": f"gexdex-api returned HTTP {response.status_code}",
                    "detail": response.text,
                    "ticker": clean_ticker
                }
    except httpx.ConnectError:
        return {
            "error": "Failed to connect to gexdex-api microservice on Synology NAS.",
            "detail": f"Could not reach {settings.GEXDEX_API_URL}. Ensure container is running.",
            "ticker": clean_ticker
        }
    except Exception as e:
        return {
            "error": f"Unexpected error querying gexdex-api: {str(e)}",
            "ticker": clean_ticker
        }
