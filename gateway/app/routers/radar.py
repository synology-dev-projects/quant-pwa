import logging
from typing import Dict, Any, List, Optional
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
import sqlalchemy as sa
import pandas as pd

from app.core.auth import get_current_user
from app.routers.flow_status import get_last_market_day

logger = logging.getLogger("quant.gateway.radar")

router = APIRouter(prefix="/api/radar", tags=["Confluence Radar"])

CREATE_GEXDEX_SNAPSHOT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS gexdex_snapshot (
    snapshot_date DATE NOT NULL,
    snapshot_time TIMESTAMP WITH TIME ZONE NOT NULL,
    ticker VARCHAR(12) NOT NULL,
    spot_price NUMERIC(12, 4),
    call_put_ratio VARCHAR(20) NOT NULL DEFAULT 'N/A',
    call_wall NUMERIC(12, 2),
    put_wall NUMERIC(12, 2),
    zero_flip NUMERIC(12, 2),
    net_gex NUMERIC(18, 2),
    net_dex NUMERIC(18, 2),
    gamma_regime VARCHAR(100),
    total_call_gex NUMERIC(18, 2),
    total_put_gex NUMERIC(18, 2),
    total_call_dex NUMERIC(18, 2),
    total_put_dex NUMERIC(18, 2),
    source_scorecards TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (snapshot_date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_gexdex_snapshot_date ON gexdex_snapshot (snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_gexdex_snapshot_ticker ON gexdex_snapshot (ticker);
"""

CREATE_UNUSUAL_FLOW_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS unusual_option_flow_te (
    flow_id VARCHAR(255) PRIMARY KEY,
    trade_date VARCHAR(10) NOT NULL,
    symbol VARCHAR(12) NOT NULL,
    strike_price NUMERIC(12, 2),
    order_type VARCHAR(20),
    premium NUMERIC(18, 2) DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""


def _get_engine():
    from common_lib.config.main_config import load_config
    from common_lib.connectors.postgres import get_postgres_engine
    config = load_config()
    return get_postgres_engine(config)


def _ensure_tables(conn: sa.Connection) -> None:
    try:
        for stmt in CREATE_GEXDEX_SNAPSHOT_TABLE_SQL.strip().split(";"):
            if stmt.strip():
                conn.execute(sa.text(stmt))
        for stmt in CREATE_UNUSUAL_FLOW_TABLE_SQL.strip().split(";"):
            if stmt.strip():
                conn.execute(sa.text(stmt))
        conn.commit()
    except Exception as ex:
        logger.warning(f"Could not auto-create missing tables: {ex}")


def _format_currency(val: Optional[float]) -> str:
    if val is None or pd.isna(val):
        return "$0"
    num = float(val)
    abs_val = abs(num)
    if abs_val >= 1_000_000_000:
        return f"${num / 1_000_000_000:.2f}B"
    elif abs_val >= 1_000_000:
        return f"${num / 1_000_000:.1f}M"
    elif abs_val >= 1_000:
        return f"${num / 1_000:.0f}K"
    return f"${num:,.0f}"


def _format_price(val: Optional[float]) -> str:
    if val is None or pd.isna(val):
        return "N/A"
    try:
        num = float(val)
        if num <= 0:
            return "N/A"
        return f"${num:,.2f}"
    except (ValueError, TypeError):
        return "N/A"


class RadarUnifiedRow(BaseModel):
    ticker: str
    snapshot_date: str
    spot_price: Optional[float] = None
    formatted_spot_price: str = "N/A"
    call_put_ratio: str = "N/A"
    prints_3d: int = 0
    prints_7d: int = 0
    premium_3d: float = 0.0
    formatted_premium_3d: str = "$0"
    premium_7d: float = 0.0
    formatted_premium_7d: str = "$0"
    call_wall: Optional[float] = None
    formatted_call_wall: str = "N/A"
    put_wall: Optional[float] = None
    formatted_put_wall: str = "N/A"
    zero_flip: Optional[float] = None
    formatted_zero_flip: str = "N/A"
    net_gex: Optional[float] = None
    formatted_net_gex: str = "N/A"
    gamma_regime: str = "Neutral"


class RadarUnifiedResponse(BaseModel):
    session_date: str
    dates_3d: List[str]
    dates_7d: List[str]
    total_tickers: int
    top_flow_ticker: Optional[str] = None
    rows: List[RadarUnifiedRow]
    available_dates: List[str]
    generated_at: str


@router.get("/dates", response_model=List[str])
def get_radar_dates(_: str = Depends(get_current_user)) -> List[str]:
    """Returns list of distinct session dates available in gexdex_snapshot."""
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            _ensure_tables(conn)
            q = sa.text("""
                SELECT DISTINCT snapshot_date
                FROM gexdex_snapshot
                ORDER BY snapshot_date DESC
            """)
            rows = conn.execute(q).scalars().all()
            return [str(r) for r in rows]
    except Exception as ex:
        logger.error(f"Failed to query radar available dates: {ex}")
        return []


@router.get("/unified-table", response_model=RadarUnifiedResponse)
def get_unified_radar_table(
    target_date: Optional[str] = Query(None, alias="date"),
    _: str = Depends(get_current_user)
) -> RadarUnifiedResponse:
    """
    Returns the unified Confluence Radar table combining GEX/DEX snapshot key levels
    and options flow metrics across trailing 3-day and 7-day trade sessions.
    Grain: (snapshot_date, ticker).
    """
    engine = _get_engine()
    with engine.connect() as conn:
        _ensure_tables(conn)
        # 1. Resolve Available Dates
        q_dates_all = sa.text("""
            SELECT DISTINCT snapshot_date
            FROM gexdex_snapshot
            ORDER BY snapshot_date DESC
        """)
        avail_dates = [str(d) for d in conn.execute(q_dates_all).scalars().all()]

        # 2. Resolve Target Session Date
        if target_date and target_date.strip():
            clean_date = target_date.strip()
        else:
            clean_date = avail_dates[0] if avail_dates else str(get_last_market_day())

        # 3. Discover Trailing Trade Sessions from unusual_option_flow_te
        q_dates = sa.text("""
            SELECT DISTINCT trade_date
            FROM unusual_option_flow_te
            WHERE trade_date <= :target_date_str
              AND strike_price > 0
            ORDER BY trade_date DESC
            LIMIT 10
        """)
        trade_dates = [str(d) for d in conn.execute(q_dates, {"target_date_str": clean_date}).scalars().all()]
        dates_3d = trade_dates[:3]
        dates_7d = trade_dates[:7]

        # 4. Fetch Snapshot rows for target date
        q_snap = sa.text("""
            SELECT 
                snapshot_date,
                ticker,
                spot_price,
                call_put_ratio,
                call_wall,
                put_wall,
                zero_flip,
                net_gex,
                net_dex,
                gamma_regime
            FROM gexdex_snapshot
            WHERE snapshot_date = :target_date
        """)
        snap_rows = conn.execute(q_snap, {"target_date": clean_date}).mappings().all()
        snap_map = {str(s["ticker"]).upper(): s for s in snap_rows}

        # 5. Fetch Flow Aggregates for trailing windows
        flow_map = {}
        if dates_7d:
            q_flow = sa.text("""
                SELECT 
                    symbol,
                    COUNT(*) FILTER (WHERE trade_date = ANY(:dates_3d)) AS prints_3d,
                    COALESCE(SUM(premium) FILTER (WHERE trade_date = ANY(:dates_3d)), 0) AS premium_3d,
                    COUNT(*) FILTER (WHERE trade_date = ANY(:dates_7d)) AS prints_7d,
                    COALESCE(SUM(premium) FILTER (WHERE trade_date = ANY(:dates_7d)), 0) AS premium_7d
                FROM unusual_option_flow_te
                WHERE trade_date = ANY(:dates_7d)
                  AND strike_price > 0
                GROUP BY symbol
            """)
            flow_rows = conn.execute(q_flow, {"dates_3d": dates_3d, "dates_7d": dates_7d}).mappings().all()
            flow_map = {str(r["symbol"]).upper(): r for r in flow_rows}

        # 6. Confluence symbols: strictly include curated watchlist tickers with GEX/DEX levels
        all_symbols = sorted(snap_map.keys())


        rows: List[RadarUnifiedRow] = []
        for sym in all_symbols:
            s = snap_map.get(sym)
            f = flow_map.get(sym, {})

            spot_val = float(s["spot_price"]) if s and s["spot_price"] is not None and not pd.isna(s["spot_price"]) else None
            cw_val = float(s["call_wall"]) if s and s["call_wall"] is not None and not pd.isna(s["call_wall"]) else None
            pw_val = float(s["put_wall"]) if s and s["put_wall"] is not None and not pd.isna(s["put_wall"]) else None
            zf_val = float(s["zero_flip"]) if s and s["zero_flip"] is not None and not pd.isna(s["zero_flip"]) else None
            gex_val = float(s["net_gex"]) if s and s["net_gex"] is not None and not pd.isna(s["net_gex"]) else None
            cpr_val = str(s["call_put_ratio"]) if s and s["call_put_ratio"] and not pd.isna(s["call_put_ratio"]) else "N/A"
            regime_val = str(s["gamma_regime"]) if s and s["gamma_regime"] and not pd.isna(s["gamma_regime"]) else "Neutral"

            p3 = int(f.get("prints_3d", 0)) if f else 0
            p7 = int(f.get("prints_7d", 0)) if f else 0
            prem3 = float(f.get("premium_3d", 0.0)) if f else 0.0
            prem7 = float(f.get("premium_7d", 0.0)) if f else 0.0

            rows.append(RadarUnifiedRow(
                ticker=sym,
                snapshot_date=clean_date,
                spot_price=spot_val,
                formatted_spot_price=_format_price(spot_val),
                call_put_ratio=cpr_val,
                prints_3d=p3,
                prints_7d=p7,
                premium_3d=prem3,
                formatted_premium_3d=_format_currency(prem3),
                premium_7d=prem7,
                formatted_premium_7d=_format_currency(prem7),
                call_wall=cw_val,
                formatted_call_wall=_format_price(cw_val),
                put_wall=pw_val,
                formatted_put_wall=_format_price(pw_val),
                zero_flip=zf_val,
                formatted_zero_flip=_format_price(zf_val),
                net_gex=gex_val,
                formatted_net_gex=_format_currency(gex_val) if gex_val is not None else "N/A",
                gamma_regime=regime_val
            ))

        # Default sort: premium_7d DESC, then prints_7d DESC
        rows.sort(key=lambda r: (r.premium_7d, r.prints_7d), reverse=True)

        top_flow_ticker = rows[0].ticker if rows and rows[0].premium_7d > 0 else None

        return RadarUnifiedResponse(
            session_date=clean_date,
            dates_3d=dates_3d,
            dates_7d=dates_7d,
            total_tickers=len(rows),
            top_flow_ticker=top_flow_ticker,
            rows=rows,
            available_dates=avail_dates,
            generated_at=datetime.now().isoformat()
        )
