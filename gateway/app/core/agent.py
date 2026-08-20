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
from app.tools.registry import tool_ui_events_var
from app.tools.gexdex_tool import get_gexdex

SYSTEM_INSTRUCTION_BASE = """You are Quant AI, an elite institutional Options & Quantitative Market Strategist built for active traders.
You operate with precision, conciseness, and deep understanding of options market structure (GEX, DEX, Gamma Regimes, Call/Put Walls, Zero Gamma Flips).

TOOL HIERARCHY & EXECUTION RULES:
1. PROPRIETARY DATA FIRST: Whenever the user asks for options exposure, GEX, DEX, gamma flip, put wall, call wall, dealer positioning, or strikes on any single or multiple stock tickers (e.g. SPY, AAPL, NVDA, TSLA, INTC, BLDP, AAOI, ADEA, SHLS), you MUST call the `get_gexdex` tool.
2. MULTI-TICKER QUERIES: Pass comma-separated ticker lists (e.g. `ticker="BLDP,AAOI,ADEA,INTC,SHLS"`) to `get_gexdex` in a single tool call.
3. WEB SEARCH: Use web search grounding ONLY when the user specifically asks about breaking news, macro events (CPI, FOMC), or earnings announcements.

RESPONSE FORMATTING RULES:
- For each ticker queried, output a clean, structured quantitative breakdown including:
  * Spot Price, Gamma Regime (Positive/Negative Gamma), and Call/Put Walls.
- Followed by a concise **Institutional Dealer Positioning Ranking** from best positioning to worst with actionable insights.
- Do NOT output markdown image syntax (such as ![...](...)) or image URLs. The client PWA automatically mounts native interactive HTML5 Canvas charts directly from data.
- Keep tone professional, analytical, and direct. Avoid fluff.
"""


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
    meta_payload = json.dumps({"type": "temporal_meta", "meta": market_meta})
    yield f"data: {meta_payload}\n\n"

    # Initialize tool UI events list for this async stream
    tool_ui_events_var.set([])

    try:
        client = create_genai_client()
    except Exception as e:
        err_payload = json.dumps({"type": "error", "message": f"Gemini Client Init Error: {str(e)}"})
        yield f"data: {err_payload}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    windowed_messages = apply_sliding_window(messages)
    if not windowed_messages:
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    last_msg = windowed_messages[-1]
    history_msgs = windowed_messages[:-1]
    active_prompt = last_msg.get("content", "")

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
        tools=callable_tools,
    )

    models_to_try = [selected_model]
    for backup in ["gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3.1-flash-lite"]:
        if backup not in models_to_try:
            models_to_try.append(backup)

    response = None
    active_model_used = selected_model
    last_error = None

    for attempt_model in models_to_try:
        try:
            if client_disconnected_fn and await client_disconnected_fn():
                return

            chat = client.chats.create(
                model=attempt_model,
                config=config,
                history=history_contents
            )

            response = await asyncio.to_thread(chat.send_message, active_prompt)
            if response:
                active_model_used = attempt_model
                break
        except Exception as err:
            err_str = str(err)
            last_error = err
            if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                await asyncio.sleep(0.3)
                continue
            else:
                break

    if not response and last_error:
        err_msg = json.dumps({"type": "error", "message": f"Streaming Error: {str(last_error)}"})
        yield f"data: {err_msg}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Yield all captured Tool UI events (single-flight chart coordinates & payload)
    captured_ui_events = tool_ui_events_var.get() or []
    for ui_event in captured_ui_events:
        if client_disconnected_fn and await client_disconnected_fn():
            return
        yield f"data: {json.dumps(ui_event)}\n\n"

    # If failover occurred, notify user
    if active_model_used != selected_model:
        failover_badge = f"> ℹ️ **Model Failover:** `{selected_model}` was experiencing temporary Google Cloud demand limits. Routed to **`{active_model_used}`**.\n\n"
        badge_payload = json.dumps({"type": "token", "content": failover_badge})
        yield f"data: {badge_payload}\n\n"

    # Stream the complete response text with pacing for natural rendering
    if response and response.text:
        words = response.text.split(" ")
        for i, word in enumerate(words):
            if client_disconnected_fn and await client_disconnected_fn():
                return
            space = " " if i < len(words) - 1 else ""
            token_payload = json.dumps({"type": "token", "content": word + space})
            yield f"data: {token_payload}\n\n"
            await asyncio.sleep(0.003)

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
