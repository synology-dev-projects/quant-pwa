import json
import asyncio
from typing import AsyncGenerator, List, Dict, Any
from google import genai
from google.genai import types

from app.config import settings
from app.core.temporal import generate_temporal_system_prompt, get_market_status
from app.core.context import apply_sliding_window
from app.tools import registry

SYSTEM_INSTRUCTION_BASE = """You are Quant AI, an elite institutional Options & Quantitative Market Strategist built for active traders.
You operate with precision, conciseness, and deep understanding of options market structure.

TOOL HIERARCHY RULES:
1. PROPRIETARY DATA FIRST: Whenever the user asks for options exposure, GEX, DEX, gamma flip, put wall, call wall, dealer positioning, or strikes on any ticker (e.g. SPY, AAPL, NVDA, TSLA, AAOI), you MUST execute the `get_gexdex` tool. Do NOT search the web for proprietary options Greek exposures.
2. WEB SEARCH FOR MACRO & NEWS: Use web search grounding ONLY when the user asks about breaking market news, earnings releases, macroeconomic data (CPI, PPI, FOMC, Fed interest rate decisions), or company catalysts.

RESPONSE FORMATTING:
- Begin with a clean, punchy breakdown of the ticker, spot price, and current Gamma Regime (e.g. Positive / Mean-Reverting vs. Negative / Volatile).
- Highlight key strike levels in bold: **Call Wall (Cap/Magnet)**, **Put Wall (Support/Floor)**, and **Gamma Flip (Regime Pivot)**.
- Explain the tactical dealer hedging implications (e.g. dealer dip-buying in positive gamma vs. delta-hedging cascade risk in negative gamma).
- Always include the chart image in markdown if provided by the tool: `![Ticker Chart](url)`.
- Keep tone professional, analytical, and direct. Avoid unnecessary conversational fluff.
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
    if selected_model != "gemini-2.5-flash":
        models_to_try.append("gemini-2.5-flash")
    if "gemini-flash-latest" not in models_to_try:
        models_to_try.append("gemini-flash-latest")

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

            # Execute chat completion with Automatic Function Calling
            response = await asyncio.to_thread(chat.send_message, active_prompt)
            if response:
                active_model_used = attempt_model
                break
        except Exception as err:
            err_str = str(err)
            last_error = err
            # If 503 or 429 high demand error, fall through to next model in list
            if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                await asyncio.sleep(0.5)
                continue
            else:
                break

    if not response and last_error:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Streaming Error: {str(last_error)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # If failover occurred, notify the user with a distinct badge
    if active_model_used != selected_model:
        failover_badge = f"> ℹ️ **Model Failover:** `{selected_model}` was experiencing temporary Google Cloud congestion (503). Routed to **`{active_model_used}`**.\n\n"
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
