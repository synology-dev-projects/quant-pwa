# ⚙️ ETL Data Pipelines & Ingestion Engines

## 1. Overview & Standardized Architecture

All ETL (Extract, Transform, Load) pipelines in the Quant System adhere to a consistent 3-stage module separation:

```mermaid
graph LR
    subgraph ExtractPhase [1. Extract (extract.py)]
        Source[External API / Portal / IBKR] --> Scraper[Session Authenticator & Scraper]
        Scraper --> Raw[Raw JSON / Dict / DF]
    end

    subgraph TransformPhase [2. Transform (transform.py)]
        Raw --> Parser[Regex Matcher & Schema Cleaner]
        Parser --> Validated[Typed Pandas DataFrame]
    end

    subgraph LoadPhase [3. Load (load.py)]
        Validated --> UpsertEngine[insert_into_table / write_to_postgres_upsert]
        UpsertEngine --> SingleFlight[Native PostgreSQL ON CONFLICT DO UPDATE]
        SingleFlight --> Destination[(PostgreSQL 16 quant_db)]
    end
```

---

## 2. Pipeline Deep Dives

### 2.1 `quant-level-pipeline`
* **Source:** TradingEdge Mighty Networks feed (`/api/v2/spaces/.../posts`).
* **Frequency:** Daily incremental cron (after market close at 16:30 ET) & manual historical backfill.
* **Extraction:** Authenticates with session cookies (`TE_COOKIE`), paginates feed, downloads attached `.txt`/`.csv` files, and falls back to HTML body parsing.
* **Parsing Engine:**
  - Extracts market session date from post title (`parser.isoparse`).
  - Matches strike price boundaries using `re.compile(r'^\s*(\d{2,6}(?:\.\d+)?)(?:\s*-\s*(\d{2,6}(?:\.\d+)?))?\s*(.*)')`.
  - Normalizes single price points (e.g. `5800 Bounce`) to `PRICE_LOW=5800.0`, `PRICE_HIGH=5800.0`.
* **Database Ingestion:** Native PostgreSQL upsert via `common_lib.connectors.postgres.insert_into_table` with `write_mode="upsert"` / `"overwrite"` and primary keys `["datetime", "ticker", "start_lvl_price"]`.
* **Target Table:** `quant_lvl_data_te` on PostgreSQL 16 `quant_db` (Port 5435).

---

### 2.2 `ibkr-historical-data-pipeline`
* **Source:** Interactive Brokers Gateway (`ib_insync` socket connection on port 4002 / 4004).
* **Supported Contracts:** Stocks (STK), Indices (IND), Futures (FUT), Options (OPT).
* **Parameters:** `symbol`, `barSizeSetting` (`1 min`, `5 mins`, `1 hour`, `1 day`), `durationStr` (`1 D`, `1 M`, `1 Y`), `whatToShow` (`TRADES`, `MIDPOINT`, `BID_ASK`).
* **Connection Lifecycle:** Dynamic client ID allocation (`random.randint(100, 9999)`), and strict `try...finally: ib.disconnect()` socket safety.
* **Database Ingestion:** Native PostgreSQL upsert via `common_lib.connectors.postgres.insert_into_table` with primary keys `["symbol", "datetime", "barsize"]`.
* **Target Table:** `ibkr_historical_te` on PostgreSQL 16 `quant_db` (Port 5435).

---

### 2.3 `mm-dex-gex-pipeline`
* **Source:** TradingEdge DEX/GEX raw options chain API.
* **Mathematical Greek Formulations:**
  $$\text{Call GEX}_K = \Gamma_K \times S \times \text{OI}_K \times 100$$
  $$\text{Put GEX}_K = -\Gamma_K \times S \times \text{OI}_K \times 100$$
  $$\text{Net GEX}_K = \text{Call GEX}_K + \text{Put GEX}_K$$
  $$\text{Net DEX}_K = (\Delta_{\text{Call}, K} \times \text{OI}_{\text{Call}, K} - |\Delta_{\text{Put}, K}| \times \text{OI}_{\text{Put}, K}) \times S \times 100$$
  where $S$ is spot price, $K$ is strike price, and $\text{OI}$ is open interest.
* **Target Table:** `MM_DEX_GEX_TE`

---

### 2.4 `unusual-option-flow-pipeline`
* **Source:** TradingEdge Institutional Option Flow Gate (`https://flow.tradingedge.club`).
* **Core Architecture:**
  - **Dynamic Site-Wide Ticker Discovery (`extract.py`):** Automatically discovers active universe tickers by parsing the landing page DOM and drop-down menu selectors, eliminating hardcoded symbol lists and capturing new tickers immediately upon publication.
  - **Automated Flow Gate Session Lifecycle:** Performs automated form-based login authentication against `https://flow.tradingedge.club/Login.aspx`, persisting session cookies with defensive retry handling.
  - **Deterministic ID Generation (`transform.py`):** Computes unique 32-character SHA-256 hashes (`flow_id`) across `(trade_date, symbol, order_type, strike_price, expiration_date, premium)` ensuring perfect idempotency during incremental upserts.
  - **Normalization & Sentiment Scoring:** Normalizes strike prices, parses OTM/ITM percentages, flags unusual volume-to-open-interest spikes (`is_unusual_oi`), and captures directional net score indicators.

#### Executable Pipelines & Standalone Scripts (`src/scripts/`):
1. **`daily_incremental.py` (Production Cron Ingestion):**
   - **Watermark Discovery:** Dynamically retrieves the latest recorded `trade_date` from PostgreSQL (`unusual_option_flow_te`), defaulting to a 30-day lookback if the table is empty.
   - **Targeted Incremental Ingestion:** Discovers all site-wide tickers and scrapes only records beyond the database watermark cutoff date.
   - **Zero-Drift Upserts:** Executes atomic PostgreSQL `ON CONFLICT (flow_id) DO UPDATE` writes.
   - **Alerting:** Dispatches NTFY priority 5 alerts on fatal exceptions while completing cleanly (`exit code 0`) when 0 new records are detected on market holidays.

2. **`manual_historical.py` (Deep Historical Backfill):**
   - **CLI Parameterization:** Supports `--symbols` (e.g. `NVDA,SPY,AAPL` or all site tickers), `--days` (default 730 days / 2 years), and `--mode` (`upsert`, `overwrite`, `ignore`).
   - **Multi-Year Extraction:** Pages through deep historical flow archives with high-efficiency batch inserts.

3. **`verify_vertical.py` (In-Situ Vertical Slice Tester):**
   - **6-Layer Verification Harness:** Executes an end-to-end dry-run validation against live production or fallback fixtures:
     1. `[1/6] Extract:` Authenticates and fetches raw flow payloads.
     2. `[2/6] Transform:` Verifies field types, OTM regex calculations, and SHA-256 hash generation.
     3. `[3/6] Load:` Tests PostgreSQL connection, table creation, and idempotency (0 duplicates on re-insertion).
     4. `[4/6] Read:` Executes single-flight multi-symbol query and formats summary via `flow_tool.py`.
     5. `[5/6] Resilience:` Simulates empty inputs, malformed records, non-existent symbols, and database timeouts to ensure zero cascading failures.
     6. `[6/6] Client UI:` Executes in-situ Node.js DOM test suite (`test_vertical_table_ui.js`) validating 31 assertions across tri-state column sorting, secondary tie-breakers, and client pagination.

* **Target Table:** `unusual_option_flow_te` on PostgreSQL 16 (Port 5435).

---

### 2.5 `gexdex-snapshot-pipeline`
* **Source:** TradingEdge DEX/GEX option models filtered by upstream institutional option flow watchlist.
* **Frequency:** Daily incremental cron at **Market Open (09:15 ET)** based on the **last completed market session data** (`get_last_market_day`).
* **Execution:**
  - Automated trigger via Synology Task Scheduler (`09:15 ET`).
  - Evaluates against `get_last_market_day()` (rolls back across weekends and NYSE market holidays).
  - Verifies presence of institutional sweeps in `unusual_option_flow_te` for target session before computing scorecard snapshots.
  - Commits atomic upserts into PostgreSQL fact table `gexdex_snapshot`.
* **Target Table:** `gexdex_snapshot` on PostgreSQL 16 `quant_db` (Port 5435).

---

## 3. Resilience, Schedulers & Alerts

1. **Daily Cycle Orchestrator (`scripts/run_daily_cycle.py`):**
   - Scheduled at **09:15 ET** (Market Open) via Synology Task Scheduler.
   - Evaluates the last completed trade day (`get_default_session_date` -> `get_last_market_day`).
   - Executes topological DAG sequence: `unusual_option_flow` -> `gexdex_snapshot` -> `market_confluence`.
2. **Failure Notification (`ntfy.py`):** Fatal exceptions trigger HTTP POST push notifications with priority 5 to `https://richntfynotifier.synology.me/alerts`.
3. **Weekend & Holiday Invariance:** When scrapers execute on non-trading days and detect 0 new records, they log an informational event and terminate with `exit code 0` to prevent false positive CI/CD alerts.
4. **In-Situ Vertical Testing:** All pipeline updates require `verify_vertical.py` execution prior to merge, enforcing 100% test coverage across live extraction, transformation, database upsert, read paths, and client DOM table rendering.

