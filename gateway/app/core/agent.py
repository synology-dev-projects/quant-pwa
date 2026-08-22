import re
import json
import uuid
import time
import asyncio
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional
from google import genai
from google.genai import types
from google.genai import errors

from app.config import settings
from app.core.temporal import generate_temporal_system_prompt, get_market_status
from app.core.context import apply_sliding_window
from app.tools import registry
from app.tools.registry import tool_ui_events_var, tool_metrics_var
from app.tools.gexdex_tool import get_gexdex

logger = logging.getLogger("quant.gateway.agent")

SYSTEM_INSTRUCTION_BASE = """You are Quant AI, an elite institutional Options & Quantitative Market Strategist built for active traders.
You operate with precision, conciseness, and deep understanding of options market structure (GEX, DEX, Gamma Regimes, Call/Put Walls, Zero Gamma Flips).

TOOL HIERARCHY & EXECUTION RULES:
1. PROPRIETARY DATA FIRST: Whenever the user asks for options exposure, GEX, DEX, gamma flip, put wall, call wall, dealer positioning, or strikes on any single or multiple stock tickers (e.g. SPY, AAPL, NVDA, TSLA, INTC, BLDP, AAOI, ADEA, SHLS), you MUST call the `get_gexdex` tool.
2. MULTI-TICKER QUERIES: Pass comma-separated ticker lists (e.g. `ticker="BLDP,AAOI,ADEA,INTC,SHLS"`) to `get_gexdex` in a single tool call.
3. MACRO & GENERAL MARKET: When the user asks about macro conditions, CPI, FOMC, calendar, or general catalysts, synthesize quantitative macroeconomic insights directly.

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
    http_opts = types.HttpOptions(
        timeout=12000,
        retry_options=types.HttpRetryOptions(attempts=1)
    )
    return genai.Client(api_key=api_key, http_options=http_opts)


_get_genai_client = create_genai_client


async def stream_chat_response(
    messages: List[Dict[str, Any]],
    model_name: str = None,
    client_disconnected_fn=None,
    trace_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    t_req_start = time.perf_counter()
    trace_id = trace_id or f"tr-{uuid.uuid4().hex[:6]}"
    selected_model = model_name or settings.DEFAULT_GEMINI_MODEL
    market_meta = get_market_status()
    temporal_prompt = generate_temporal_system_prompt()
    full_system_instruction = f"{SYSTEM_INSTRUCTION_BASE}\n\n{temporal_prompt}"

    # Initialize tool UI events and metrics for this async stream
    tool_ui_events_var.set([])
    tool_metrics_var.set({
        "tool_latency_ms": 0.0,
        "cache_status": "MISS",
        "retry_count": 0,
        "first_tool_start": None,
        "last_tool_end": None
    })

    # 1. Yield temporal metadata immediately
    meta_payload = json.dumps({"type": "temporal_meta", "meta": market_meta})
    yield f"data: {meta_payload}\n\n"

    try:
        client = create_genai_client()
    except Exception as e:
        err_payload = json.dumps({"type": "error", "message": f"Gemini Client Init Error: {str(e)}"})
        yield f"data: {err_payload}\n\n"
        server_ms = (time.perf_counter() - t_req_start) * 1000.0
        metrics_payload = json.dumps({
            "trace_id": trace_id,
            "tool_decision_ms": 0.0,
            "tool_ms": 0.0,
            "cache_status": "MISS",
            "retry_attempts": 0,
            "synthesis_ttft_ms": 0.0,
            "llm_ttft_ms": 0.0,
            "token_count": 0,
            "tok_per_sec": 0.0,
            "server_total_ms": round(server_ms, 1)
        })
        yield f"event: metrics\ndata: {metrics_payload}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    windowed_messages = apply_sliding_window(messages)
    if not windowed_messages:
        server_ms = (time.perf_counter() - t_req_start) * 1000.0
        metrics_payload = json.dumps({
            "trace_id": trace_id,
            "tool_decision_ms": 0.0,
            "tool_ms": 0.0,
            "cache_status": "MISS",
            "retry_attempts": 0,
            "synthesis_ttft_ms": 0.0,
            "llm_ttft_ms": 0.0,
            "token_count": 0,
            "tok_per_sec": 0.0,
            "server_total_ms": round(server_ms, 1)
        })
        yield f"event: metrics\ndata: {metrics_payload}\n\n"
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

    from app.mcp.client import mcp_client_manager
    callable_tools = list(registry.get_callable_map().values()) + mcp_client_manager.get_all_tools()

    config = types.GenerateContentConfig(
        system_instruction=full_system_instruction,
        temperature=0.2,
        tools=callable_tools,
    )

    models_to_try = [selected_model]
    # Model Candidate Routing Hierarchy (Fallback on transient 429/503)
    fallback_hierarchy = [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
        "gemini-3.7-flash"
    ]
    for backup in fallback_hierarchy:
        if backup not in models_to_try:
            models_to_try.append(backup)

    response = None
    active_model_used = selected_model
    last_error = None
    prompt_submit_time = time.perf_counter()

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
                last_error = None
                break
        except (errors.APIError, Exception) as err:
            err_str = str(err)
            last_error = err
            logger.warning(
                f"[{trace_id}] Model {attempt_model} failed with transient error: {err_str}. Fast failover to next candidate."
            )
            
            # Robust AFC Fallback: If tool execution threw an exception, retry with direct synthesis
            try:
                fallback_config = types.GenerateContentConfig(
                    system_instruction=full_system_instruction,
                    temperature=0.3
                )
                chat_fb = client.chats.create(
                    model=attempt_model,
                    config=fallback_config,
                    history=history_contents
                )
                response = await asyncio.to_thread(chat_fb.send_message, active_prompt)
                if response:
                    active_model_used = attempt_model
                    last_error = None
                    break
            except Exception as fb_err:
                logger.warning(f"[{trace_id}] Model {attempt_model} AFC direct synthesis fallback error: {fb_err}")

            # Fast failover to next candidate model (< 500ms without sleeping)
            continue

    if not response and last_error:
        err_msg = json.dumps({"type": "error", "message": f"Streaming Error: {str(last_error)}"})
        yield f"data: {err_msg}\n\n"
        metrics_dict = tool_metrics_var.get() or {}
        tool_ms = max(0.0, float(metrics_dict.get("tool_latency_ms", 0.0)))
        cache_status = metrics_dict.get("cache_status", "MISS")
        retries = max(0, int(metrics_dict.get("retry_count", 0)))
        first_tool_start = metrics_dict.get("first_tool_start")
        tool_decision_ms = max(0.0, (first_tool_start - t_req_start) * 1000.0) if first_tool_start else 0.0
        server_ms = (time.perf_counter() - t_req_start) * 1000.0
        metrics_payload = json.dumps({
            "trace_id": trace_id,
            "tool_decision_ms": round(tool_decision_ms, 1),
            "tool_ms": round(tool_ms, 1),
            "cache_status": cache_status,
            "retry_attempts": retries,
            "synthesis_ttft_ms": 0.0,
            "llm_ttft_ms": round(tool_decision_ms, 1),
            "token_count": 0,
            "tok_per_sec": 0.0,
            "server_total_ms": round(server_ms, 1)
        })
        yield f"event: metrics\ndata: {metrics_payload}\n\n"
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
    token_count = 0
    stream_start_time = None
    stream_end_time = None

    if response and response.text:
        words = response.text.split(" ")
        token_count = len(words)
        stream_start_time = time.perf_counter()
        
        for i, word in enumerate(words):
            if client_disconnected_fn and await client_disconnected_fn():
                return
            space = " " if i < len(words) - 1 else ""
            token_payload = json.dumps({"type": "token", "content": word + space})
            yield f"data: {token_payload}\n\n"
            await asyncio.sleep(0.003)
        stream_end_time = time.perf_counter()

    # Latency tracking: Tool Decision (Round 1), Synthesis TTFT (Round 2), and Total LLM TTFT
    metrics_dict = tool_metrics_var.get() or {}
    tool_ms = max(0.0, float(metrics_dict.get("tool_latency_ms", 0.0)))
    cache_status = metrics_dict.get("cache_status", "MISS")
    retries = max(0, int(metrics_dict.get("retry_count", 0)))
    first_tool_start = metrics_dict.get("first_tool_start")
    last_tool_end = metrics_dict.get("last_tool_end")

    if first_tool_start is not None or tool_ms > 0:
        tool_decision_ms = max(0.0, (first_tool_start - t_req_start) * 1000.0) if first_tool_start is not None else 0.0
        if stream_start_time is not None:
            if last_tool_end is not None:
                synthesis_ttft_ms = max(0.0, (stream_start_time - last_tool_end) * 1000.0)
            else:
                synthesis_ttft_ms = max(0.0, (stream_start_time - prompt_submit_time) * 1000.0)
        else:
            synthesis_ttft_ms = 0.0
    else:
        tool_decision_ms = 0.0
        if stream_start_time is not None:
            synthesis_ttft_ms = max(0.0, (stream_start_time - prompt_submit_time) * 1000.0)
        else:
            synthesis_ttft_ms = 0.0

    total_ttft_ms = tool_decision_ms + synthesis_ttft_ms

    # Calculate tokens per second
    if stream_start_time and stream_end_time and stream_end_time > stream_start_time:
        duration_sec = stream_end_time - stream_start_time
        tok_per_sec = (token_count / duration_sec) if duration_sec > 0 else 0.0
    elif token_count > 0:
        total_llm_sec = time.perf_counter() - prompt_submit_time
        tok_per_sec = (token_count / total_llm_sec) if total_llm_sec > 0 else 0.0
    else:
        tok_per_sec = 0.0

    server_ms = max(0.0, (time.perf_counter() - t_req_start) * 1000.0)

    logger.info(
        f"[{trace_id}] Stream metrics: tool_decision_ms={round(tool_decision_ms, 1)}, tool_ms={round(tool_ms, 1)}, "
        f"cache={cache_status}, retries={retries}, synthesis_ttft_ms={round(synthesis_ttft_ms, 1)}, "
        f"llm_ttft_ms={round(total_ttft_ms, 1)}, tokens={token_count}, tok_per_sec={round(tok_per_sec, 1)}, "
        f"server_total_ms={round(server_ms, 1)}"
    )

    # Final metrics SSE frame
    metrics_payload = json.dumps({
        "trace_id": trace_id,
        "tool_decision_ms": round(tool_decision_ms, 1),
        "tool_ms": round(tool_ms, 1),
        "cache_status": cache_status,
        "retry_attempts": retries,
        "synthesis_ttft_ms": round(synthesis_ttft_ms, 1),
        "llm_ttft_ms": round(total_ttft_ms, 1),
        "token_count": token_count,
        "tok_per_sec": round(tok_per_sec, 1),
        "server_total_ms": round(server_ms, 1)
    })
    yield f"event: metrics\ndata: {metrics_payload}\n\n"

    # Done SSE frame
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
