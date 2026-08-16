import re
import json
import asyncio
from typing import AsyncGenerator, List, Dict, Any, Optional
from google import genai
from google.genai import types

from app.config import settings
from app.core.temporal import generate_temporal_system_prompt, get_market_status
from app.core.context import apply_sliding_window
from app.tools import registry
from app.tools.gexdex_tool import get_gexdex

SYSTEM_INSTRUCTION_BASE = """You are Quant AI, an elite institutional Options & Quantitative Market Strategist built for active traders.
You operate with precision, conciseness, and deep understanding of options market structure.

TOOL HIERARCHY RULES:
1. PROPRIETARY DATA FIRST: Whenever the user asks for options exposure, GEX, DEX, gamma flip, put wall, call wall, dealer positioning, or strikes on any ticker (e.g. SPY, AAPL, NVDA, TSLA, AAOI), you MUST utilize the proprietary Greek exposures.
2. WEB SEARCH FOR MACRO & NEWS: Use web search grounding ONLY when the user asks about breaking market news, earnings releases, macroeconomic data (CPI, PPI, FOMC, Fed interest rate decisions), or company catalysts.

RESPONSE FORMATTING:
- Begin with a clean, punchy breakdown of the ticker, spot price, and current Gamma Regime (e.g. Positive / Mean-Reverting vs. Negative / Volatile).
- Highlight key strike levels in bold: **Call Wall (Cap/Magnet)**, **Put Wall (Support/Floor)**, and **Gamma Flip (Regime Pivot)**.
- Explain the tactical dealer hedging implications (e.g. dealer dip-buying in positive gamma vs. delta-hedging cascade risk in negative gamma).
- Always include the chart image in markdown if provided: `![Ticker Chart](url)`.
- Keep tone professional, analytical, and direct. Avoid conversational filler.
"""

COMMON_NON_TICKERS = {
    "THE", "FOR", "AND", "GEX", "DEX", "CALL", "PUT", "WALL", "SPOT", "AI",
    "WHAT", "SHOW", "GIVE", "TELL", "HOW", "WHY", "CAN", "YOU", "ARE", "THIS",
    "FROM", "WITH", "CHART", "FLIP", "ZERO", "DELTA", "GAMMA", "LEVELS", "STRIKE",
    "PRICE", "TODAY", "OPEN", "CLOSE", "HIGH", "LOW", "RATE", "NEWS", "NOW"
}


def extract_potential_tickers(text: str) -> List[str]:
    """Extracts uppercase ticker symbols (e.g. AAOI, NVDA, AAPL) excluding common English words."""
    words = re.findall(r'\b[A-Za-z]{1,5}\b', text)
    found = []
    for w in words:
        clean = w.upper().strip()
        if clean not in COMMON_NON_TICKERS and len(clean) >= 2:
            if clean not in found:
                found.append(clean)
    return found


def create_genai_client() -> genai.Client:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in environment or config.")
    return genai.Client(api_key=api_key)


async def stream_chat_response(
    messages: List[Dict[str, Any]],
    model_name: str = None,
    client_disconnected_fn=None
) -> AsyncGenerator[str, None]:
    selected_model = model_name or settings.DEFAULT_GEMINI_MODEL
    market_meta = get_market_status()
    temporal_prompt = generate_temporal_system_prompt()
    full_system_instruction = f"{SYSTEM_INSTRUCTION_BASE}\n\n{temporal_prompt}"

    # 1. Yield temporal metadata immediately
    yield f"data: {json.dumps({'type': 'temporal_meta', 'meta': market_meta})}\n\n"

    try:
        client = create_genai_client()
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Gemini Client Init Error: {str(e)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    windowed_messages = apply_sliding_window(messages)
    if not windowed_messages:
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    last_msg = windowed_messages[-1]
    history_msgs = windowed_messages[:-1]
    active_prompt = last_msg.get("content", "")

    # 2. Hybrid Optimization: Attempt 1-Turn Direct Pre-Fetch
    candidate_tickers = extract_potential_tickers(active_prompt)
    prefetched_context_blocks = []
    
    if candidate_tickers:
        yield f"data: {json.dumps({'type': 'tool_start', 'name': 'get_gexdex', 'args': {'tickers': candidate_tickers}})}\n\n"
        for t in candidate_tickers[:2]:  # support up to 2 tickers concurrently
            try:
                gex_res = await asyncio.to_thread(get_gexdex, t)
                if gex_res and "error" not in gex_res:
                    block = f"""[LIVE GEX/DEX DATA FOR {t}]:
- Spot Price: ${gex_res.get('spot_price', 'N/A')}
- Net GEX: ${gex_res.get('net_gex', 'N/A')}
- Net DEX: ${gex_res.get('net_dex', 'N/A')}
- Zero GEX Flip Level: ${gex_res.get('zero_gex_level', 'N/A')}
- Key Gamma Strike / Call Wall: ${gex_res.get('key_gamma_strike', 'N/A')}
- Call / Put Ratio: {gex_res.get('call_put_ratio', 'N/A')}
- Options Chart Markdown: {gex_res.get('markdown_image', '')}
"""
                    prefetched_context_blocks.append(block)
            except Exception:
                pass

    # Format history contents
    history_contents = []
    for msg in history_msgs:
        role = "user" if msg.get("role") == "user" else "model"
        history_contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg.get("content", ""))]
            )
        )

    callable_tools = list(registry.get_callable_map().values())

    config = types.GenerateContentConfig(
        system_instruction=full_system_instruction,
        temperature=0.2,
        tools=callable_tools if not prefetched_context_blocks else None,  # No tool overhead if pre-fetched
    )

    models_to_try = [selected_model]
    for backup in ["gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3.1-flash-lite"]:
        if backup not in models_to_try:
            models_to_try.append(backup)

    response = None
    active_model_used = selected_model
    last_error = None

    effective_prompt = active_prompt
    if prefetched_context_blocks:
        effective_prompt = f"{active_prompt}\n\n" + "\n\n".join(prefetched_context_blocks)

    for attempt_model in models_to_try:
        try:
            if client_disconnected_fn and await client_disconnected_fn():
                return

            chat = client.chats.create(
                model=attempt_model,
                config=config,
                history=history_contents
            )

            response = await asyncio.to_thread(chat.send_message, effective_prompt)
            if response:
                active_model_used = attempt_model
                break
        except Exception as err:
            err_str = str(err)
            last_error = err
            if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                await asyncio.sleep(0.4)
                continue
            else:
                break

    if not response and last_error:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Streaming Error: {str(last_error)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # If failover occurred, notify the user with a distinct badge
    if active_model_used != selected_model:
        failover_badge = f"> ℹ️ **Model Failover:** `{selected_model}` was experiencing temporary Google Cloud quota/demand limits. Routed to **`{active_model_used}`**.\n\n"
        yield f"data: {json.dumps({'type': 'token', 'content': failover_badge})}\n\n"

    # Stream the completed text response in smooth tokens
    if response and response.text:
        words = response.text.split(" ")
        for i, word in enumerate(words):
            if client_disconnected_fn and await client_disconnected_fn():
                break
            space = " " if i < len(words) - 1 else ""
            yield f"data: {json.dumps({'type': 'token', 'content': word + space})}\n\n"
            await asyncio.sleep(0.012)

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
