# Quant AI - Mobile Chat PWA & Agent Gateway (`quant-pwa`)

A high-performance, mobile-first **Quant AI Chat Progressive Web App** powered by a server-side **Agent Gateway** hosted on your Synology NAS. 

It provides **instant zero-token digest card delivery**, **batch multi-ticker portfolio pre-fetching (up to 8 tickers concurrently)**, streaming Server-Sent Events (SSE) to mobile phones (over Home Wi-Fi or 5G Cellular via Cloudflare Tunnel), authenticated passcodes, and direct integration with `gexdex-api` and **Google Gemini 3.5/3.7**.

---

## 🏗️ Architecture

```text
Mobile Phone (PWA / iOS / Android)
       │ (HTTPS / Cloudflare Tunnel)
       ▼
   Nginx Frontend (Port 8096 Dev / 8095 Prod)
       │
       ▼
 FastAPI Gateway (:8000)
       ├── Declarative Tool Calling (Pure LLM Orchestration)
       ├── Parallel Multi-Ticker Resolution (gexdex-api LAN)
       └── Real-Time Token Streaming (Server-Sent Events)
```

---

## 🎯 Design Goals & Gateway Innovations

1. **Pure LLM Autonomous Tool Calling**:
   - Eliminates fragile regex string parsing. Google Gemini uses full natural language intelligence to identify valid stock tickers from complex user prompts (e.g. `"ok here are my holdings: BLDP, AAOI, ADEA, INTC, SHLS..."`) and automatically batches them into a single `get_gexdex` tool invocation.
2. **Deterministic Multi-Ticker Execution**:
   - Resolves all portfolio metrics and renders dual-sided GEX/DEX horizontal bar charts concurrently across `ThreadPoolExecutor` worker pools on the Synology NAS.
3. **Unified Single-Flight SSE & Client-Side HTML5 Canvas Rendering**:
   - Eliminates raster image lag and failed image loading. The Gateway emits single-flight `tool_ui` events containing granular strike distribution coordinates directly over the chat SSE stream.
   - The browser mounts a high-performance **HTML5 Canvas** component (`QuantChart`), rendering interactive dual-panel GEX & DEX charts with touch/hover tooltips, dashed Spot/Wall lines, and offline history persistence in under 10ms.
4. **Comparative Institutional Ranking**:
   - Automatically provides dealer positioning summaries, gamma regimes, Call/Put walls, and ranked trade positioning.
5. **Resilient Network Timeouts**:
   - 30-second timeout guards and retry mechanisms ensure heavy multi-asset queries never drop or throw 502 Bad Gateway errors.

---

## 🐳 Synology NAS Deployment & Ports

- **Dev Environment**: Port `8096` (`http://192.168.1.68:8096`)
- **Prod Environment**: Port `8095` (`http://192.168.1.68:8095`)

Launch stack via Docker Compose:
```bash
docker compose up -d --build
```

---

## 🔐 Security & Session Architecture

The PWA is guarded by a glassmorphic **Password Protected Lock Screen (Auth Gate)** backed by **6-Hour Cryptographic HMAC-SHA256 Signed Sessions** and **FAANG-grade Brute-Force Rate Limiting**:

1. **Master Password Never Stored Client-Side**:
   - The user inputs the master passcode once (`RichQuantDemo` / `APP_PASSCODE`).
   - The Gateway validates it using constant-time comparison (`secrets.compare_digest`) and returns a signed 6-hour JWT session token (`POST /api/auth/login`).
   - The browser stores **only** this temporary session token in `localStorage`.
2. **5-Attempt Rate Limiting & 15-Minute Lockout**:
   - Allows up to **5 failed login attempts within a 5-minute sliding window**.
   - On the 5th failure, the client IP is automatically locked out for **15 minutes** (`HTTP 429 Too Many Requests` with `Retry-After: 900`).
   - Includes **500ms anti-automation tarpitting** to slow down automated dictionary attacks.
   - Successful login immediately clears the failed attempt counter.
3. **Automatic 6-Hour Session Expiration**:
   - Every session automatically expires after 6 hours.
   - Any API request with an expired token is rejected with `HTTP 401 Unauthorized`, prompting the lock screen to reappear.
4. **Manual App Lock**:
   - Tapping **"Lock App"** in the Settings drawer immediately wipes the local session token and returns to the lock screen.
5. **Hermetic Multi-Environment Isolation**:
   - Nginx uses dynamic `envsubst` templates (`/etc/nginx/templates/default.conf.template`) to strictly isolate ingress routing:
     - `quant-frontend-dev` (:8096) &rarr; `http://quant-gateway-dev:8000/api/`
     - `quant-frontend-prod` (:8095) &rarr; `http://quant-gateway-prod:8000/api/`
   - Eliminates Docker DNS alias collisions across shared networks.
6. **Ephemeral Dev Lifecycle**:
   - Pushing to `develop` spins up the isolated Dev stack (port 8096) for testing.
   - Pushing to `master` deploys Prod (port 8095) and automatically purges the ephemeral Dev stack to conserve NAS memory and CPU.

---

## 🔌 Adding New Skills (Extensibility)

Create a new tool file in `gateway/app/tools/levels_tool.py`:
```python
from app.tools.registry import register_tool

@register_tool(
    name="get_quant_levels",
    description="Fetch proprietary pivot, support, and resistance levels for a ticker."
)
async def get_quant_levels(ticker: str):
    return {"ticker": ticker, "pivot": 5800, "r1": 5850}
```
Import it in `gateway/app/tools/__init__.py` — the Gateway automatically registers it with Gemini with zero frontend changes needed.
