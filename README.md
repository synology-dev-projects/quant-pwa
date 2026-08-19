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
3. **Comparative Institutional Ranking**:
   - Automatically provides dealer positioning summaries, gamma regimes, Call/Put walls, and ranked trade positioning.
4. **Resilient Network Timeouts**:
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

## 🔐 Security & 6-Hour Signed Session Authentication

The PWA is guarded by a glassmorphic **Password Protected Lock Screen (Auth Gate)** powered by cryptographic **6-Hour HMAC-SHA256 Signed Sessions**:

1. **Master Password Never Stored Client-Side**:
   - The user inputs the master passcode once.
   - The Gateway validates it against `APP_PASSCODE` and issues an HMAC-SHA256 session token (`POST /api/auth/login`).
   - The client stores **only** this temporary token in `localStorage`.
2. **Automatic 6-Hour Session Expiration**:
   - Every session automatically expires after 6 hours.
   - Any API request with an expired token is rejected with `HTTP 401 Unauthorized`, prompting the lock screen to reappear.
3. **Manual App Lock**:
   - Tapping **"Lock App"** in the Settings drawer immediately invalidates the local session token and returns to the lock screen.
4. **All Environments Protected**:
   - Operates consistently across both **develop** (port 8096) and **production** (port 8095 / Cloudflare Tunnel).

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
