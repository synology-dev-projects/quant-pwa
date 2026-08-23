import re
import json
import uuid
import time
import asyncio
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional, Tuple
from google import genai
from google.genai import types
from google.genai import errors

from app.config import settings
from app.core.temporal import generate_temporal_system_prompt, get_market_status
from app.core.context import apply_sliding_window
from app.tools import registry
from app.tools.registry import tool_ui_events_var, tool_metrics_var
from app.tools.gexdex_tool import get_gexdex
from app.tools.flow_tool import get_unusual_flow

logger = logging.getLogger("quant.gateway.agent")

SYSTEM_INSTRUCTION_BASE = """You are Quant AI, an institutional Options & Quantitative Market Strategist.
Operate with analytical precision, clarity, and deep understanding of options microstructure (GEX, DEX, Gamma Regimes, Call/Put Walls, Zero Gamma Flips) and institutional options flow.

EXECUTION RULES:
1. PROPRIETARY DATA: Call `get_gexdex` for options exposure. When querying multiple tickers (e.g. FANG, cohorts), ALWAYS pass them as a single comma-separated batch string in ONE tool call: `get_gexdex(ticker="META,AAPL,AMZN,NFLX,GOOGL")`. Do NOT call `get_gexdex` sequentially one-by-one.
2. UNUSUAL OPTIONS FLOW: Call `get_unusual_flow` to inspect institutional options flow, sweeps, blocks, open interest anomalies, and smart money bets for a stock ticker symbol.
3. MACRO & STRATEGY: Synthesize macroeconomic insights (FOMC, CPI, rates, cross-asset correlation) directly.
4. FORMATTING: Output structured quantitative breakdowns followed by actionable dealer positioning rankings.
5. NO_IMAGE_SYNTAX: Never emit markdown image syntax (![...] or .png URLs). Charts are rendered natively via client HTML5 Canvas.
6. STRICT COMPLETENESS: You MUST output an explicit breakdown row for EVERY requested ticker with zero exceptions. Never drop or truncate any requested symbol. If data for a ticker is unavailable or errored, output its row explicitly as `• TICKER: [Options Data Unavailable / Delisted]` and provide the full quantitative breakdown for all remaining tickers.
"""

CROSS_SYNTHESIS_KEYWORDS = {
    "macro", "fomc", "cpi", "fed", "rates", "compare",
    "strategy", "risk", "levels", "correlation", "portfolio",
    "treasury", "yield", "vix", "inflation", "jobs", "payrolls"
}


def evaluate_synthesis_tier(
    prompt: Optional[str] = "",
    history: Optional[List[Any]] = None,
    tools_called_count: int = 0
) -> Tuple[str, str, int]:
    """
    Dynamically evaluate whether a query requires Tier 1 (Fast Worker) or Tier 2 (Strategic Thinking).
    Returns (tier_label, target_model, thinking_budget).
    - Tier 2 ('STRATEGIC'): tools_called_count >= 2, macro/cross-synthesis keywords, or multi-ticker comparison.
    - Tier 1 ('FAST'): single ticker lookups or direct queries without deep synthesis keywords.
    """
    if tools_called_count >= 2:
        return ("STRATEGIC", settings.TIER2_STRATEGIC_MODEL, 512)

    texts = []
    if prompt:
        texts.append(str(prompt))
    if history:
        for item in history:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                content = item.get("content", "")
                if isinstance(content, str):
                    texts.append(content)
            elif hasattr(item, "parts") and item.parts:
                for part in item.parts:
                    if hasattr(part, "text") and part.text:
                        texts.append(part.text)
            elif hasattr(item, "text") and item.text:
                texts.append(item.text)

    combined_text = " ".join(texts).lower()

    for kw in CROSS_SYNTHESIS_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", combined_text):
            return ("STRATEGIC", settings.TIER2_STRATEGIC_MODEL, 512)

    if re.search(r"\b[a-z]{1,5}(?:[\.\/][a-z])?\s*,\s*[a-z]{1,5}(?:[\.\/][a-z])?\b", combined_text):
        return ("STRATEGIC", settings.TIER2_STRATEGIC_MODEL, 512)

    return ("FAST", settings.TIER1_FAST_WORKER_MODEL, 0)


def detect_query_thinking_budget(prompt: str, history: Optional[List[Any]] = None) -> int:
    """
    Dynamically determine thinking budget based on query complexity.
    Returns 512 for multi-source/macro/cross-ticker synthesis and 0 for fast single-ticker lookups.
    """
    _, _, budget = evaluate_synthesis_tier(prompt=prompt, history=history, tools_called_count=0)
    return budget


def create_genai_client() -> genai.Client:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in environment or config.")
    http_opts = types.HttpOptions(
        timeout=60000,
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
    market_meta = get_market_status()
    temporal_prompt = generate_temporal_system_prompt()
    full_system_instruction = f"{SYSTEM_INSTRUCTION_BASE}\n\n{temporal_prompt}"

    # Initialize tool UI events and metrics for this async stream
    tool_ui_events_var.set([])
    tool_metrics_var.set({
        "tool_latency_ms": 0.0,
        "cache_status": "MISS",
        "retry_count": 0,
        "tools_called_count": 0,
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
            "tier_used": "fast",
            "model_used": model_name or settings.DEFAULT_GEMINI_MODEL,
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
            "tier_used": "fast",
            "model_used": model_name or settings.DEFAULT_GEMINI_MODEL,
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

    # Dynamic Split-Model Tier Routing Evaluation
    tier_label, target_model, budget = evaluate_synthesis_tier(
        prompt=active_prompt,
        history=history_contents,
        tools_called_count=0
    )

    if model_name:
        target_model = model_name
        if model_name == settings.TIER2_STRATEGIC_MODEL:
            tier_label = "STRATEGIC"
            budget = 512

    # Model Candidate Routing Hierarchy
    if tier_label == "STRATEGIC":
        raw_hierarchy = [target_model, settings.TIER2_FALLBACK_MODEL, settings.TIER1_FAST_WORKER_MODEL]
    else:
        if model_name:
            raw_hierarchy = [target_model, settings.TIER1_FAST_WORKER_MODEL, settings.TIER2_FALLBACK_MODEL]
        else:
            raw_hierarchy = [settings.TIER1_FAST_WORKER_MODEL, settings.TIER2_FALLBACK_MODEL]

    models_to_try = []
    for m in raw_hierarchy:
        if m and m not in models_to_try:
            models_to_try.append(m)

    thinking_cfg = None
    if hasattr(types, "ThinkingConfig") and budget > 0 and tier_label == "STRATEGIC":
        try:
            thinking_cfg = types.ThinkingConfig(thinking_budget=budget)
        except Exception as e:
            logger.warning(f"[{trace_id}] ThinkingConfig initialization failed: {e}")
            thinking_cfg = None

    config = types.GenerateContentConfig(
        system_instruction=full_system_instruction,
        temperature=0.2,
        tools=callable_tools,
        thinking_config=thinking_cfg,
    )

    response = None
    active_model_used = models_to_try[0] if models_to_try else (model_name or settings.DEFAULT_GEMINI_MODEL)
    intended_model = active_model_used
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
            
            # 1. Fallback: If thinking_config was active, retry without thinking_config
            if thinking_cfg is not None:
                try:
                    no_think_config = types.GenerateContentConfig(
                        system_instruction=full_system_instruction,
                        temperature=0.2,
                        tools=callable_tools,
                    )
                    chat_nth = client.chats.create(
                        model=attempt_model,
                        config=no_think_config,
                        history=history_contents
                    )
                    response = await asyncio.to_thread(chat_nth.send_message, active_prompt)
                    if response:
                        active_model_used = attempt_model
                        last_error = None
                        break
                except Exception as nth_err:
                    logger.warning(f"[{trace_id}] Model {attempt_model} without thinking_config fallback error: {nth_err}")

            # 2. Robust AFC Fallback: If tool execution threw an exception, retry with direct synthesis
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

    metrics_dict = tool_metrics_var.get() or {}
    tools_called = metrics_dict.get("tools_called_count", 0)
    if tools_called >= 2:
        tier_label = "STRATEGIC"

    if not response and last_error:
        err_msg = json.dumps({"type": "error", "message": f"Streaming Error: {str(last_error)}"})
        yield f"data: {err_msg}\n\n"
        tool_ms = max(0.0, float(metrics_dict.get("tool_latency_ms", 0.0)))
        cache_status = metrics_dict.get("cache_status", "MISS")
        retries = max(0, int(metrics_dict.get("retry_count", 0)))
        first_tool_start = metrics_dict.get("first_tool_start")
        tool_decision_ms = max(0.0, (first_tool_start - t_req_start) * 1000.0) if first_tool_start else 0.0
        server_ms = (time.perf_counter() - t_req_start) * 1000.0
        metrics_payload = json.dumps({
            "trace_id": trace_id,
            "tier_used": tier_label.lower(),
            "model_used": active_model_used,
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
    if active_model_used != intended_model:
        failover_badge = f"> **[ROUTING NOTICE]** `{intended_model}` experienced cloud capacity constraints. Dispatched via **`{active_model_used}`**.\n\n"
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
        f"[{trace_id}] Stream metrics: tier={tier_label.lower()}, model={active_model_used}, tool_decision_ms={round(tool_decision_ms, 1)}, tool_ms={round(tool_ms, 1)}, "
        f"cache={cache_status}, retries={retries}, synthesis_ttft_ms={round(synthesis_ttft_ms, 1)}, "
        f"llm_ttft_ms={round(total_ttft_ms, 1)}, tokens={token_count}, tok_per_sec={round(tok_per_sec, 1)}, "
        f"server_total_ms={round(server_ms, 1)}"
    )

    # Final metrics SSE frame
    metrics_payload = json.dumps({
        "trace_id": trace_id,
        "tier_used": tier_label.lower(),
        "model_used": active_model_used,
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
