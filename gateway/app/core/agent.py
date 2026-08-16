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
- Deliver clean, institutional quantitative breakdowns.
- Always include the chart image in markdown if provided: `![Ticker Chart](url)`.
- Keep tone professional, analytical, and direct. Avoid conversational filler.
"""

COMMON_NON_TICKERS = {
    "THE", "FOR", "AND", "GEX", "DEX", "CALL", "PUT", "WALL", "SPOT", "AI",
    "WHAT", "SHOW", "GIVE", "TELL", "HOW", "WHY", "CAN", "YOU", "ARE", "THIS",
    "FROM", "WITH", "CHART", "FLIP", "ZERO", "DELTA", "GAMMA", "LEVELS", "STRIKE",
    "PRICE", "TODAY", "OPEN", "CLOSE", "HIGH", "LOW", "RATE", "NEWS", "NOW",
    "REFRESH", "FRESH", "UPDATE", "RELOAD", "FORCE"
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


def format_quant_digest_card(data: Dict[str, Any], is_refresh: bool = False) -> str:
    """
    Renders an institutional Markdown Quant Digest Card with zero token cost.
    """
    ticker = data.get("ticker", "TICKER")
    spot = data.get("spot_price", 0.0)
    regime = data.get("gamma_regime", "Positive Gamma")
    cp_ratio = data.get("call_put_ratio", 1.0)
    
    call_wall = data.get("call_wall", data.get("key_gamma_strike", "N/A"))
    put_wall = data.get("put_wall", "N/A")
    gamma_flip = data.get("zero_gex_level", "N/A")
    centroid = data.get("gamma_centroid", spot)
    
    exp_move_dlr = data.get("expected_move_dollars", 0.0)
    exp_move_pct = data.get("expected_move_pct", 3.5)
    exp_low = data.get("expected_range_low", round(spot * 0.965, 2))
    exp_high = data.get("expected_range_high", round(spot * 1.035, 2))
    
    gex_above_pct = data.get("gex_above_pct", 50.0)
    gex_below_pct = round(100.0 - gex_above_pct, 1)
    dex_above_pct = data.get("dex_above_pct", 50.0)
    dex_below_pct = round(100.0 - dex_above_pct, 1)
    front_week_pct = data.get("front_week_gex_pct", 45.0)
    dominant_exp = data.get("dominant_expiration", "Near-term")
    
    pin_risk = data.get("pin_risk_level", "MODERATE")
    squeeze_risk = data.get("gamma_squeeze_risk", "LOW")
    cascade_risk = data.get("cascade_drop_risk", "LOW")
    
    chart_md = data.get("markdown_image", "")
    data_badge = "🔄 *Live On-Demand Refresh*" if is_refresh else "💾 *1-Hour Snapshot Cache*"

    card = f"""### 🟢 **{ticker} — Institutional Options & GEX Digest**
*{data_badge}*

* **Spot Price:** **`${spot:.2f}`**
* **Gamma Regime:** **`{regime}`**
* **Call / Put Gamma Ratio:** **`{cp_ratio:.2f}`**

---

#### 🧱 **Key Pivot Matrix**
* **Call Wall (Resistance / Magnet):** **`${call_wall}`**
* **Put Wall (Support Floor):** **`${put_wall}`**
* **Zero GEX / Gamma Flip:** **`${gamma_flip}`**
* **Gamma Centroid (Center of Gravity):** **`${centroid}`**
* **1-Week Expected Move:** **`±${exp_move_dlr:.2f} (±{exp_move_pct:.1f}%)`** $\rightarrow$ Range: **`${exp_low:.2f} — ${exp_high:.2f}`**

---

#### ⚖️ **Exposure Imbalances & Time Skew**
* **GEX Distribution:** **`{gex_above_pct}% Above Spot`** vs. **`{gex_below_pct}% Below Spot`**
* **DEX Distribution:** **`{dex_above_pct}% Above Spot`** vs. **`{dex_below_pct}% Below Spot`**
* **Front-Week Velocity (0–7 DTE):** **`{front_week_pct}%`** of Total Gamma *(Dominant Expiry: `{dominant_exp}`)*
* **Risk Signals:** Pinning Risk: **`{pin_risk}`** | Squeeze Risk: **`{squeeze_risk}`** | Cascade Risk: **`{cascade_risk}`**

---

{chart_md}
"""
    return card


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
    is_force_refresh = bool(re.search(r'\b(REFRESH|FRESH|UPDATE|RELOAD|FORCE)\b', active_prompt, re.IGNORECASE))
    candidate_tickers = extract_potential_tickers(active_prompt)
    prefetched_cards = []
    prefetched_ai_contexts = []
    
    if candidate_tickers:
        yield f"data: {json.dumps({'type': 'tool_start', 'name': 'get_gexdex', 'args': {'tickers': candidate_tickers, 'force_refresh': is_force_refresh}})}\n\n"
        for t in candidate_tickers[:2]:  # support up to 2 tickers concurrently
            try:
                gex_res = await asyncio.to_thread(get_gexdex, t, 50, 25, is_force_refresh)
                if gex_res and "error" not in gex_res:
                    card = format_quant_digest_card(gex_res, is_refresh=is_force_refresh)
                    prefetched_cards.append(card)
                    
                    ai_ctx = f"Ticker {t}: Spot ${gex_res.get('spot_price')}, Call Wall ${gex_res.get('call_wall')}, Put Wall ${gex_res.get('put_wall')}, GEX Above: {gex_res.get('gex_above_pct')}%, Front-Week GEX: {gex_res.get('front_week_gex_pct')}%"
                    prefetched_ai_contexts.append(ai_ctx)
            except Exception:
                pass

    # Stream the structured Digest Card immediately (Instant zero-token delivery)
    if prefetched_cards:
        for card_content in prefetched_cards:
            words = card_content.split(" ")
            for i, word in enumerate(words):
                if client_disconnected_fn and await client_disconnected_fn():
                    return
                space = " " if i < len(words) - 1 else ""
                yield f"data: {json.dumps({'type': 'token', 'content': word + space})}\n\n"
                await asyncio.sleep(0.003)

        # Micro-prompt for Gemini tactical synthesis
        effective_prompt = f"Provide 2-3 concise, high-level institutional dealer positioning takeaways based on these metrics: " + "; ".join(prefetched_ai_contexts) + f". Context from user prompt: '{active_prompt}'."
    else:
        effective_prompt = active_prompt

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
        tools=callable_tools if not prefetched_cards else None,  # No tool overhead if pre-fetched
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

            response = await asyncio.to_thread(chat.send_message, effective_prompt)
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

    if not response and last_error and not prefetched_cards:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Streaming Error: {str(last_error)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # If failover occurred and AI generated a response, notify user
    if active_model_used != selected_model and not prefetched_cards:
        failover_badge = f"> ℹ️ **Model Failover:** `{selected_model}` was experiencing temporary Google Cloud demand limits. Routed to **`{active_model_used}`**.\n\n"
        yield f"data: {json.dumps({'type': 'token', 'content': failover_badge})}\n\n"

    # Stream AI synthesis
    if response and response.text:
        yield f"data: {json.dumps({'type': 'token', 'content': '\n\n#### 🧠 **Institutional Dealer Takeaways**\n'})}\n\n"
        words = response.text.split(" ")
        for i, word in enumerate(words):
            if client_disconnected_fn and await client_disconnected_fn():
                break
            space = " " if i < len(words) - 1 else ""
            yield f"data: {json.dumps({'type': 'token', 'content': word + space})}\n\n"
            await asyncio.sleep(0.012)

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
