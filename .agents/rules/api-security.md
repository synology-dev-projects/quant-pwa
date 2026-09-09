---
trigger: "glob:**/gexdex-api/**,glob:**/quant-pwa/gateway/**"
---

# API Security, DTE Math & Streaming Rules

1. **Fail-Closed API Keys:** Microservices must fail fast on startup if `API_KEY` or `APP_PASSCODE` is missing. Never default to placeholder strings.
2. **Constant-Time Comparison:** Use `secrets.compare_digest(api_key, expected_key)` to prevent timing side-channel attacks.
3. **CORS Isolation:** Never allow wildcard `allow_origins=["*"]` when `allow_credentials=True`. Whitelist explicit trusted origins.
4. **DTE Math:** Ensure datetime timezone normalization is evaluated prior to `.days` extraction:
   ```python
   exp_date = pd.to_datetime(row.get("expiration"))
   if exp_date.tzinfo is None:
       exp_date = exp_date.tz_localize(timezone.utc)
   dte = (exp_date - now_dt).days
   ```
5. **Streaming Sub-300ms:** SSE endpoints in the Gateway must yield tokens natively via `chat.send_message_stream()`. Do not buffer the full response before streaming.
