# Quant AI - Mobile Chat PWA & Agent Gateway

A high-performance, mobile-first **Quant AI Chat Application** powered by a server-side **Agent Gateway** hosted on your Synology NAS. 

It provides **sub-300ms Time-to-First-Token (TTFT)** streaming to your phone (over **Home Wi-Fi** or **5G/LTE Cellular** via Cloudflare Tunnel), secures access via an **App Passcode**, displays live market timestamps/freshness badges, feeds direct `gexdex-api` metrics into **Google Gemini 3.7 Flash / Pro**, and features a **modular tab system** and **pluggable skill registry**.

---

## 🏗️ Architecture

```text
Phone (5G / Wi-Fi) ===[Cloudflare Tunnel HTTPS]===> Nginx (:8080)
                                                        |
                                            FastAPI Gateway (:8000)
                                               /               \
                          [LAN <5ms] gexdex-api          Google Gemini 3.7
```

---

## 🚀 Quick Start & Local Testing

### 1. Gateway Setup (Local Python)
```bash
cd gateway
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt

# Run tests
pytest tests/

# Run gateway locally
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Testing (Local Web Server)
You can open `frontend/index.html` directly using VS Code Live Server or python http.server:
```bash
cd frontend
python -m http.server 8080
```
Open `http://localhost:8080` in your browser.

---

## 🐳 Synology NAS Deployment (Docker Compose)

1. Copy the `quant-pwa/` folder to your Synology NAS (e.g. `/volume1/docker/quant-pwa`).
2. Create your `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```
3. Fill in your credentials:
   - `GEMINI_API_KEY`: Your Google Gemini API Key.
   - `APP_PASSCODE`: Your private security passcode for the app.
   - `GEXDEX_API_KEY`: Your Synology `gexdex-api` key.
   - `CLOUDFLARE_TUNNEL_TOKEN`: Your Cloudflare Tunnel token.
4. Launch the stack:
   ```bash
   docker compose up -d --build
   ```

---

## 📱 Mobile Installation (Add to Home Screen)

1. Open your custom HTTPS domain (e.g. `https://quant.yourdomain.com`) in Safari (iOS) or Chrome (Android).
2. **iOS Safari**: Tap the **Share** button $\rightarrow$ Select **"Add to Home Screen"**.
3. **Android Chrome**: Tap the three dots $\rightarrow$ Select **"Install App"** / **"Add to Home Screen"**.
4. In the app, tap the **⚙️ Settings** gear and enter your `APP_PASSCODE`.

---

## 🔌 Adding New Skills (Extensibility)

To add a new skill to the AI assistant (e.g. `quant_levels`):
1. Create a new tool file in `gateway/app/tools/levels_tool.py`:
   ```python
   from app.tools.registry import register_tool

   @register_tool(
       name="get_quant_levels",
       description="Fetch proprietary pivot, support, and resistance levels for a ticker."
   )
   async def get_quant_levels(ticker: str):
       # Call your microservice
       return {"ticker": ticker, "pivot": 5800, "r1": 5850}
   ```
2. Import it in `gateway/app/tools/__init__.py`.
3. The Gateway automatically registers it with Gemini — zero frontend code changes needed!

---

## 📑 Adding New Tabs to the PWA

In `frontend/src/tabs/tab_manager.js`, call:
```javascript
TabManager.registerTab({
  id: 'levels',
  title: 'Levels',
  iconSvg: '<svg>...</svg>',
  render: (container) => {
    container.innerHTML = '<div class="levels-view">Custom Levels UI</div>';
  }
});
```
