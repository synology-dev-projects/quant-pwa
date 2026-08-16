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
1. PROPRIETARY DATA FIRST: Whenever the user asks for options exposure, GEX, DEX, gamma flip, put wall, call wall, dealer positioning, or strikes on any ticker (e.g. SPY, AAPL, NVDA, TSLA), you MUST execute the `get_gexdex` tool. Do NOT search the web for proprietary options Greek exposures.
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
    """
    Executes the Gemini streaming loop with tool calling and yields SSE formatted event payloads.
    Yields:
      data: {"type": "token", "content": "..."}
      data: {"type": "tool_start", "name": "...", "args": {...}}
      data: {"type": "tool_end", "name": "...", "result": {...}}
      data: {"type": "temporal_meta", "meta": {...}}
      data: {"type": "done"}
    """
    selected_model = model_name or settings.DEFAULT_GEMINI_MODEL
    market_meta = get_market_status()
    temporal_prompt = generate_temporal_system_prompt()
    full_system_instruction = f"{SYSTEM_INSTRUCTION_BASE}\n\n{temporal_prompt}"

    # Yield temporal metadata first to update UI timestamp badge
    yield f"data: {json.dumps({'type': 'temporal_meta', 'meta': market_meta})}\n\n"

    try:
        client = create_genai_client()
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Gemini Client Init Error: {str(e)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Prepare sliding window messages
    windowed_messages = apply_sliding_window(messages)
    
    # Format contents for GenAI SDK
    formatted_contents = []
    for msg in windowed_messages:
        role = "user" if msg.get("role") == "user" else "model"
        content_text = msg.get("content", "")
        formatted_contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=content_text)]
            )
        )

    # Collect tool definitions
    callable_tools = list(registry.get_callable_map().values())
    
    # Configure Gemini request
    config = types.GenerateContentConfig(
        system_instruction=full_system_instruction,
        temperature=0.3,
        tools=callable_tools,
    )

    try:
        # Check disconnect before sending
        if client_disconnected_fn and await client_disconnected_fn():
            return

        # Execute streaming call
        response_stream = client.models.generate_content_stream(
            model=selected_model,
            contents=formatted_contents,
            config=config
        )

        for chunk in response_stream:
            if client_disconnected_fn and await client_disconnected_fn():
                # Client dropped mobile connection - abort immediately to save tokens
                break

            # Handle text tokens
            if chunk.text:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk.text})}\n\n"
                await asyncio.sleep(0.005)  # smooth micro-yield

            # Handle automatic tool execution feedback if present
            if chunk.function_calls:
                for fc in chunk.function_calls:
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': fc.name, 'args': fc.args})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Streaming Error: {str(e)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
