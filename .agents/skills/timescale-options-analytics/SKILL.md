---
name: timescale-options-analytics
description: >-
  Query optimization, continuous aggregates, and indexing patterns for
  PostgreSQL 16 & TimescaleDB options tick and snapshot data.
  Use when writing options analytics queries, tuning SQL performance, or running /timescale-opt.
---

# 🗄️ TimescaleDB Options Analytics Engine (`/timescale-opt`)

Use this skill when optimizing options microstructure queries, designing hypertables, or tuning sub-5ms query SLAs on the Synology NAS PostgreSQL instance.

---

## 1. Options Microstructure Indexing Blueprint

Options flow tables (`unusual_option_flow_te`) and snapshot tables (`gexdex_snapshot`) require composite B-Tree and partial indexes to maintain sub-5ms query execution as data grows past millions of rows.

```sql
-- 1. Index for Ticker Session Filtering (Cockpit search)
CREATE INDEX IF NOT EXISTS idx_flow_sym_trade_date 
ON unusual_option_flow_te (symbol, trade_date DESC);

-- 2. Partial Index for Whale Prints (> $1.0M Premium)
CREATE INDEX IF NOT EXISTS idx_flow_whale_prints 
ON unusual_option_flow_te (trade_date DESC, premium_num DESC)
WHERE premium_num >= 1000000;

-- 3. Composite Index for Notable OTM Speculation
-- Cast dates to avoid operator does not exist errors
CREATE INDEX IF NOT EXISTS idx_flow_otm_speculation
ON unusual_option_flow_te (trade_date, otm_pct)
WHERE otm_pct >= 10.0;
```

---

## 2. Fast Strike Distribution & Wall Calculation Query

Optimized query template to compute Spot, Net GEX, Call Wall, and Put Wall in a single scan:

```sql
WITH strike_aggregates AS (
    SELECT 
        strike_price,
        SUM(CASE WHEN option_type = 'CALL' THEN gex_val ELSE 0 END) AS call_gex,
        SUM(CASE WHEN option_type = 'PUT'  THEN gex_val ELSE 0 END) AS put_gex,
        SUM(gex_val) AS net_gex
    FROM options_chain_snapshot
    WHERE symbol = :symbol 
      AND snapshot_date = :snapshot_date
    GROUP BY strike_price
),
ranked_walls AS (
    SELECT 
        strike_price,
        net_gex,
        ROW_NUMBER() OVER (ORDER BY call_gex DESC) AS call_wall_rank,
        ROW_NUMBER() OVER (ORDER BY put_gex ASC)   AS put_wall_rank
    FROM strike_aggregates
)
SELECT 
    (SELECT strike_price FROM ranked_walls WHERE call_wall_rank = 1) AS call_wall,
    (SELECT strike_price FROM ranked_walls WHERE put_wall_rank = 1)  AS put_wall,
    COALESCE(
        (SELECT strike_price 
         FROM strike_aggregates 
         WHERE net_gex >= 0 
         ORDER BY strike_price ASC 
         LIMIT 1), 
        0.0
    ) AS zero_flip;
```

---

## 3. Safe Schema Rules on Synology NAS
1. **Always use parameterized queries**: Avoid string interpolation to prevent SQL injection and enable query plan caching.
2. **Explicit type casting**: If subtracting dates stored as strings (`VARCHAR`), always cast explicitly:
   - PostgreSQL: `(CAST(expiration_date AS DATE) - CAST(trade_date AS DATE))`
   - SQLite fallback: `CAST(ROUND(julianday(expiration_date) - julianday(trade_date)) AS INTEGER)`
3. **No full table locks**: Use `CONCURRENTLY` for index creation in production migrations.
