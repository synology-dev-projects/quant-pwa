---
name: fastapi-sse-streaming
description: >-
  Best practices for building robust Server-Sent Events (SSE) streaming endpoints
  with FastAPI and Gemini LLM token streaming in Quant PWA.
  Use when adding live AI synthesis, streaming endpoints, or running /sse.
---

# 🚀 FastAPI SSE Streaming Engine (`/sse`, `/streaming`)

Use this skill when building or modifying real-time Server-Sent Events (SSE) streaming endpoints in the FastAPI Gateway.

---

## 1. Gateway SSE Endpoint Architecture

Endpoints streaming live LLM market synthesis or flow alerts must adhere to this pattern:

```python
import asyncio
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/market", tags=["Market Streaming"])

async def generate_synthesis_stream(symbol: str, as_of_date: str) -> AsyncGenerator[str, None]:
    """
    Streams Markdown synthesis chunks using standard SSE formatting.
    Sends heartbeat pings to prevent proxy/browser socket timeouts.
    """
    try:
        # 1. Yield initial handshake header
        yield f"event: message\ndata: 🔍 Analyzing {symbol} microstructure for {as_of_date}...\n\n"
        await asyncio.sleep(0.05)

        # 2. Query data context & stream LLM tokens
        # e.g. using Gemini client:
        # response = client.models.generate_content_stream(...)
        # for chunk in response:
        #     if chunk.text:
        #         yield f"event: message\ndata: {chunk.text}\n\n"
        
        # 3. Always send terminal [DONE] event
        yield "event: message\ndata: [DONE]\n\n"

    except asyncio.CancelledError:
        # Client disconnected cleanly
        logger.info(f"Client disconnected from {symbol} synthesis stream.")
    except Exception as ex:
        logger.error(f"Error during SSE stream: {ex}", exc_info=True)
        yield f"event: message\ndata: \n\n⚠️ Streaming error: {str(ex)}\n\n"
        yield "event: message\ndata: [DONE]\n\n"

@router.get("/synthesis/stream")
async def stream_synthesis(
    symbol: str = Query(..., min_length=1, max_length=10),
    as_of_date: str = Query(...)
):
    return StreamingResponse(
        generate_synthesis_stream(symbol, as_of_date),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no", # Disable Nginx/Synology reverse proxy buffering
        }
    )
```

---

## 2. Client-Side SWR Stream Consumer Recipe

Frontend consumption in Vanilla JS components:

```javascript
async function consumeStream(url, containerElement, onComplete) {
  containerElement.innerHTML = '<span class="status-dot dot-fast"></span> Synthesizing market flow...';
  
  let accumulatedMarkdown = '';
  const response = await fetch(url);
  if (!response.ok) {
    containerElement.innerHTML = '⚠️ Failed to connect to stream.';
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || ''; // keep trailing chunk

    for (const block of lines) {
      const dataLine = block.split('\n').find(l => l.startsWith('data: '));
      if (!dataLine) continue;

      const chunk = dataLine.slice(6);
      if (chunk.includes('[DONE]')) {
        if (onComplete) onComplete(accumulatedMarkdown);
        return;
      }

      accumulatedMarkdown += chunk;
      containerElement.innerHTML = renderMarkdown(accumulatedMarkdown);
    }
  }
}
```

---

## 3. Financial AI Guardrails Checklist
- [ ] **Zero Financial Advice**: Strict instruction in prompt forbidding buy/sell/targets.
- [ ] **ADHD Brevity**: Max 3 bullet points, high-density bolded numbers.
- [ ] **No Raw Code Dumps**: Prevent Gemini from wrapping answers in backtick markdown blocks.
