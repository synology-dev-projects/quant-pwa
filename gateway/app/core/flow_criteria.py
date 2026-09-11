"""
gateway/app/core/flow_criteria.py
Single Source of Truth for Institutional Flow Outlier Detection & Formatting.

Shared across:
- Cockpit: synthesis.py (single ticker scope)
- Flow Tab: flow_synthesis.py (market-wide scope across all tickers)

Rules:
1. TOP PREMIUM: Any print appearing on the active session date that ranks in the
   top 3 highest premiums ever recorded for that specific ticker.
2. NOTABLE OTM: Out-of-the-money speculation with ABS(otm_pct) >= 10.0% and DTE <= 30 days
   from the active session date.
3. Strict Segregation: Bullish and Bearish contracts are evaluated independently;
   bearish contracts NEVER subtract from bullish contracts.
4. Structured Sub-Bullet Output:
   • **Notable Flow**:
     • **TOP PREMIUM**:
       - TICKER $XX.XM PREMIUM (1st)
     • **NOTABLE OTM**:
       - TICKER XX% OTM exp 2 weeks
   If either sub-category is empty, outputs "- NONE FOUND".
5. Zero Adjectives / Telegraphic Language Mandate.
"""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import sqlalchemy as sa
import logging

logger = logging.getLogger("quant.gateway.flow_criteria")

# Configurable Filter Thresholds
TOP_PREMIUM_RANKS: Tuple[int, ...] = (1, 2, 3)
MIN_TICKER_RECORDS_FOR_RANKING: int = 10
NOTABLE_OTM_MIN_PCT: float = 10.0
NOTABLE_OTM_MAX_DTE: int = 30


def format_currency(val: Optional[float]) -> str:
    """Format dollar premium into clean, compact string ($XX.XM, $XX.XB, $XXK)."""
    if val is None:
        return "$0"
    abs_val = abs(val)
    if abs_val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.2f}B"
    elif abs_val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    elif abs_val >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:,.0f}"


def format_dte_exp(dte: int) -> str:
    """Format days-to-expiry into clean, compact human string (exp X days / exp X weeks)."""
    if dte <= 0:
        return "exp 0 days"
    if dte < 7:
        return f"exp {dte} days"
    weeks = round(dte / 7.0)
    if weeks <= 1:
        return "exp 1 week"
    return f"exp {weeks} weeks"


def format_rank_suffix(rank: int) -> str:
    """Return ordinal rank string (1st, 2nd, 3rd, 4th)."""
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(rank, f"{rank}th")


def format_notable_flow_markdown(
    top_premium_prints: List[Dict[str, Any]],
    notable_otm_prints: List[Dict[str, Any]]
) -> str:
    """
    Renders standard structured markdown for Notable Flow.
    Strictly follows:
    • **Notable Flow**:
      • **TOP PREMIUM**:
        - TICKER $XX.XM PREMIUM (1st)
      • **NOTABLE OTM**:
        - TICKER XX% OTM exp 2 weeks
    With "- NONE FOUND" if either is empty.
    """
    lines = [
        "• **Notable Flow**:",
        "  • **TOP PREMIUM**:"
    ]

    tp = top_premium_prints or []
    if tp:
        for p in tp:
            sym = str(p.get("symbol", "")).upper()
            prem = p.get("formatted_premium") or format_currency(p.get("premium"))
            rank = p.get("rank", 1)
            rank_str = format_rank_suffix(rank)
            lines.append(f"    - {sym} {prem} PREMIUM ({rank_str})")
    else:
        lines.append("    - NONE FOUND")

    lines.append("  • **NOTABLE OTM**:")

    otm = notable_otm_prints or []
    if otm:
        for o in otm:
            sym = str(o.get("symbol", "")).upper()
            otm_pct = abs(float(o.get("otm_pct", 0.0)))
            dte = int(o.get("dte", 0))
            exp_str = format_dte_exp(dte)
            lines.append(f"    - {sym} {otm_pct:.0f}% OTM {exp_str}")
    else:
        lines.append("    - NONE FOUND")

    return "\n".join(lines)


def extract_ticker_notable_flow(
    records: List[Dict[str, Any]],
    spot: float,
    session_date: Optional[str] = None,
    min_ticker_records: int = MIN_TICKER_RECORDS_FOR_RANKING
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extracts Notable Flow for a single ticker (used in Cockpit).
    Evaluates only prints from session_date (or latest date in records if not passed).
    For a flow to be rated 1st, 2nd, or 3rd, the ticker must have at least min_ticker_records (10) in the db.
    """
    if not records or spot <= 0:
        return [], []

    # Determine target session date
    if not session_date:
        trade_dates = [str(r.get("TRADE_DATE", ""))[:10] for r in records if r.get("TRADE_DATE")]
        session_date = max(trade_dates) if trade_dates else None

    if not session_date:
        return [], []

    # 1. Rank ALL records for this ticker by premium DESC only if ticker has at least min_ticker_records (10)
    top_premium_prints: List[Dict[str, Any]] = []
    if len(records) >= min_ticker_records:
        sorted_by_premium = sorted(
            records,
            key=lambda r: float(r.get("PREMIUM") or 0.0),
            reverse=True
        )

        for rank, r in enumerate(sorted_by_premium, start=1):
            if rank > max(TOP_PREMIUM_RANKS):
                break
            r_date = str(r.get("TRADE_DATE", ""))[:10]
            if r_date == session_date:
                prem = float(r.get("PREMIUM") or 0.0)
                sym = str(r.get("SYMBOL", "")).upper()
                top_premium_prints.append({
                    "symbol": sym,
                    "premium": prem,
                    "formatted_premium": format_currency(prem),
                    "rank": rank,
                    "order_type": str(r.get("ORDER_TYPE", "")),
                    "date": r_date
                })

    # 2. Extract Notable OTM from session_date
    notable_otm_prints: List[Dict[str, Any]] = []
    for r in records:
        r_date = str(r.get("TRADE_DATE", ""))[:10]
        if r_date != session_date:
            continue

        try:
            strike = float(r.get("STRIKE_PRICE") or 0.0)
            if strike <= 0:
                continue

            order_type = str(r.get("ORDER_TYPE", "")).upper()
            exp_date_str = str(r.get("EXPIRATION_DATE", ""))[:10]

            if r_date and exp_date_str:
                t_dt = datetime.strptime(r_date, "%Y-%m-%d")
                exp_dt = datetime.strptime(exp_date_str, "%Y-%m-%d")
                dte = (exp_dt - t_dt).days
            else:
                dte = 999

            if 0 <= dte <= NOTABLE_OTM_MAX_DTE:
                # Calculate OTM percentage
                otm_pct = 0.0
                if "CALL" in order_type and strike > spot:
                    otm_pct = ((strike - spot) / spot) * 100.0
                elif "PUT" in order_type and strike < spot:
                    otm_pct = ((spot - strike) / spot) * 100.0

                if otm_pct >= NOTABLE_OTM_MIN_PCT:
                    prem = float(r.get("PREMIUM") or 0.0)
                    sym = str(r.get("SYMBOL", "")).upper()
                    notable_otm_prints.append({
                        "symbol": sym,
                        "strike": strike,
                        "otm_pct": otm_pct,
                        "dte": dte,
                        "premium": prem,
                        "formatted_premium": format_currency(prem),
                        "order_type": order_type,
                        "date": r_date
                    })
        except Exception:
            continue

    # Sort OTM prints by premium DESC
    notable_otm_prints.sort(key=lambda x: x["premium"], reverse=True)

    return top_premium_prints, notable_otm_prints


def extract_session_notable_flow_db(
    conn: sa.Connection,
    session_date: str,
    min_ticker_records: int = MIN_TICKER_RECORDS_FOR_RANKING
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extracts Notable Flow across all tickers from database for session_date (used in Flow tab).
    For a flow to be rated 1st, 2nd, or 3rd, the ticker must have at least min_ticker_records (10) in the db.
    """
    if not session_date:
        return [], []

    # 1. Query prints from session_date that rank in top 3 all-time for symbols with at least min_ticker_records (10)
    query_top_premium = sa.text("""
        WITH ticker_counts AS (
            SELECT symbol, COUNT(*) AS record_count
            FROM unusual_option_flow_te
            WHERE strike_price > 0
            GROUP BY symbol
            HAVING COUNT(*) >= :min_records
        ),
        ranked_flow AS (
            SELECT 
                f.flow_id,
                f.trade_date,
                f.symbol,
                f.order_type,
                f.strike_price,
                f.strike_otm_pct,
                f.expiration_date,
                f.premium,
                DENSE_RANK() OVER (PARTITION BY f.symbol ORDER BY f.premium DESC) as all_time_rank
            FROM unusual_option_flow_te f
            JOIN ticker_counts tc ON f.symbol = tc.symbol
            WHERE f.strike_price > 0
        )
        SELECT *
        FROM ranked_flow
        WHERE trade_date = :session_date
          AND all_time_rank <= 3
        ORDER BY premium DESC
    """)

    top_premium_prints: List[Dict[str, Any]] = []
    try:
        rows_tp = conn.execute(
            query_top_premium,
            {"session_date": session_date, "min_records": min_ticker_records}
        ).mappings().all()
        for r in rows_tp:
            prem = float(r["premium"])
            top_premium_prints.append({
                "symbol": str(r["symbol"]).upper(),
                "order_type": str(r["order_type"]),
                "strike": float(r["strike_price"]),
                "premium": prem,
                "formatted_premium": format_currency(prem),
                "rank": int(r["all_time_rank"]),
                "expiration_date": str(r["expiration_date"])
            })
    except Exception as e:
        logger.warning(f"Failed to query session top premium flow: {e}")

    # 2. Query Notable OTM prints for session_date
    is_sqlite = getattr(conn.dialect, "name", "") == "sqlite"
    dte_expr = (
        "CAST(ROUND(julianday(expiration_date) - julianday(trade_date)) AS INTEGER)"
        if is_sqlite
        else "(CAST(expiration_date AS DATE) - CAST(trade_date AS DATE))"
    )

    query_notable_otm = sa.text(f"""
        SELECT 
            symbol,
            order_type,
            strike_price,
            strike_otm_pct,
            expiration_date,
            trade_date,
            premium,
            {dte_expr} as dte
        FROM unusual_option_flow_te
        WHERE trade_date = :session_date
          AND strike_price > 0
          AND ABS(strike_otm_pct) >= :min_otm_pct
          AND {dte_expr} >= 0
          AND {dte_expr} <= :max_dte
        ORDER BY premium DESC
    """)

    notable_otm_prints: List[Dict[str, Any]] = []
    try:
        rows_otm = conn.execute(
            query_notable_otm,
            {
                "session_date": session_date,
                "min_otm_pct": NOTABLE_OTM_MIN_PCT,
                "max_dte": NOTABLE_OTM_MAX_DTE
            }
        ).mappings().all()
        for r in rows_otm:
            prem = float(r["premium"])
            notable_otm_prints.append({
                "symbol": str(r["symbol"]).upper(),
                "order_type": str(r["order_type"]),
                "strike": float(r["strike_price"]),
                "otm_pct": float(r["strike_otm_pct"]),
                "dte": int(r["dte"]) if r["dte"] is not None else 0,
                "premium": prem,
                "formatted_premium": format_currency(prem)
            })
    except Exception as e:
        logger.warning(f"Failed to query session notable OTM flow: {e}")

    return top_premium_prints, notable_otm_prints
