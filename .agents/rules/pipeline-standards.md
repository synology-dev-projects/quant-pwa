---
trigger: "glob:**/*-pipeline/src/**"
---

# Data Pipeline & Scraper Engineering Rules

1. **Incremental Cutoff Logic:** Compare `item_date > cutoff_date` directly. Never add day offsets (e.g. `+ timedelta(days=1)`), which causes silent 24-hour data loss.
2. **Regex Width:** Price and strike regex matchers must use `\d{2,6}(?:\.\d+)?` to cover 3-digit tickers (SPY/QQQ) and 5-digit indices (NDX/DJIA).
3. **Safe Attachments:** Only overwrite parsed body text if downloaded attachment content is verified non-empty.
4. **Retry & Backoff:** All outbound HTTP requests must specify explicit `timeout=(5.0, 15.0)` and use `@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))`.
5. **Weekend/Holiday Exits:** When scrapers find 0 new items on non-trading days, log an informational notice and exit cleanly with code `0`.
