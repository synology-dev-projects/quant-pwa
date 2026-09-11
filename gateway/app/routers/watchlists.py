import re
import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
import sqlalchemy as sa

from app.core.auth import get_current_user
from app.core.index_validator import validate_ticker_in_indices
from app.core.quote_feed import get_batch_quotes, WatchlistQuotesResponse, QuoteItem

logger = logging.getLogger("quant.gateway.watchlists")

router = APIRouter(prefix="/api/watchlists", tags=["Watchlists"])

CREATE_WATCHLISTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS quant_watchlists (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quant_watchlist_tickers (
    watchlist_id VARCHAR(64) REFERENCES quant_watchlists(id) ON DELETE CASCADE,
    ticker VARCHAR(12) NOT NULL,
    indices VARCHAR(255) DEFAULT '',
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (watchlist_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_ticker ON quant_watchlist_tickers(ticker);
"""

_custom_engine: Optional[sa.Engine] = None


def get_engine() -> sa.Engine:
    global _custom_engine
    if _custom_engine is not None:
        return _custom_engine
    try:
        from common_lib.config.main_config import load_config
        from common_lib.connectors.postgres import get_postgres_engine
        config = load_config()
        return get_postgres_engine(config)
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL engine: {e}")
        fallback = sa.create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=sa.pool.StaticPool
        )
        _ensure_tables(fallback)
        return fallback


def set_custom_engine(engine: Optional[sa.Engine]) -> None:
    global _custom_engine
    _custom_engine = engine
    if engine is not None:
        _ensure_tables(engine)


def _ensure_tables(engine: sa.Engine) -> None:
    try:
        with engine.begin() as conn:
            for stmt in CREATE_WATCHLISTS_TABLE_SQL.strip().split(";"):
                if stmt.strip():
                    conn.execute(sa.text(stmt))
    except Exception as ex:
        logger.warning(f"Could not initialize watchlist tables: {ex}")


class CreateWatchlistRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Name of the new watchlist")


class AddTickerRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12, description="Ticker symbol to validate and add")


class WatchlistTickerItem(BaseModel):
    ticker: str
    indices: List[str] = Field(default_factory=list)
    added_at: Optional[str] = None


class WatchlistResponse(BaseModel):
    id: str
    name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    tickers: List[WatchlistTickerItem] = Field(default_factory=list)


def _slugify(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name).strip().lower()
    s = re.sub(r"[-\s]+", "_", s)
    return s[:40] or "watchlist"


def _bootstrap_default_watchlist_if_empty(engine: sa.Engine) -> None:
    try:
        with engine.begin() as conn:
            cnt = conn.execute(sa.text("SELECT COUNT(*) FROM quant_watchlists")).scalar() or 0
            if cnt == 0:
                wl_id = "wl_core_watchlist"
                conn.execute(
                    sa.text("INSERT INTO quant_watchlists (id, name) VALUES (:id, :name)"),
                    {"id": wl_id, "name": "Core Watchlist"}
                )
                default_tickers = ["NVDA", "SPY", "QQQ", "AAPL"]
                for t in default_tickers:
                    is_valid, indices = validate_ticker_in_indices(t)
                    indices_str = ",".join(indices) if is_valid else ""
                    conn.execute(
                        sa.text("""
                            INSERT INTO quant_watchlist_tickers (watchlist_id, ticker, indices)
                            VALUES (:wid, :ticker, :indices)
                        """),
                        {"wid": wl_id, "ticker": t, "indices": indices_str}
                    )
    except Exception as ex:
        logger.warning(f"Failed to bootstrap default watchlist: {ex}")


@router.get("", response_model=List[WatchlistResponse])
def get_all_watchlists(current_user: str = Depends(get_current_user)):
    engine = get_engine()
    _ensure_tables(engine)
    _bootstrap_default_watchlist_if_empty(engine)

    try:
        with engine.connect() as conn:
            wl_rows = conn.execute(sa.text("""
                SELECT id, name, created_at, updated_at 
                FROM quant_watchlists 
                ORDER BY created_at ASC
            """)).mappings().all()

            ticker_rows = conn.execute(sa.text("""
                SELECT watchlist_id, ticker, indices, added_at 
                FROM quant_watchlist_tickers 
                ORDER BY added_at ASC
            """)).mappings().all()

            tickers_by_wl: Dict[str, List[WatchlistTickerItem]] = {}
            for tr in ticker_rows:
                wid = tr["watchlist_id"]
                if wid not in tickers_by_wl:
                    tickers_by_wl[wid] = []
                ind_list = [i.strip() for i in (tr["indices"] or "").split(",") if i.strip()]
                added_str = str(tr["added_at"]) if tr["added_at"] else None
                tickers_by_wl[wid].append(WatchlistTickerItem(
                    ticker=tr["ticker"],
                    indices=ind_list,
                    added_at=added_str
                ))

            res: List[WatchlistResponse] = []
            for wl in wl_rows:
                wid = wl["id"]
                res.append(WatchlistResponse(
                    id=wid,
                    name=wl["name"],
                    created_at=str(wl["created_at"]) if wl["created_at"] else None,
                    updated_at=str(wl["updated_at"]) if wl["updated_at"] else None,
                    tickers=tickers_by_wl.get(wid, [])
                ))
            return res
    except Exception as ex:
        logger.error(f"Error fetching watchlists: {ex}")
        raise HTTPException(status_code=500, detail=f"Failed to query watchlists: {ex}")


class AvailableTickerItem(BaseModel):
    ticker: str
    indices: List[str] = Field(default_factory=list)


@router.get("/available-tickers", response_model=List[AvailableTickerItem])
def get_available_tickers(current_user: str = Depends(get_current_user)):
    """Returns all supported index and options flow tickers for client-side dropdown selection."""
    from app.core.index_validator import get_all_available_tickers as _get_tickers
    return [AvailableTickerItem(**item) for item in _get_tickers()]


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
def create_watchlist(req: CreateWatchlistRequest, current_user: str = Depends(get_current_user)):
    clean_name = req.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Watchlist name cannot be empty.")

    engine = get_engine()
    _ensure_tables(engine)

    slug = _slugify(clean_name)
    wl_id = f"wl_{slug}_{uuid.uuid4().hex[:6]}"
    now_dt = datetime.now(timezone.utc)

    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text("""
                    INSERT INTO quant_watchlists (id, name, created_at, updated_at) 
                    VALUES (:id, :name, :created_at, :updated_at)
                """),
                {"id": wl_id, "name": clean_name, "created_at": now_dt, "updated_at": now_dt}
            )

        return WatchlistResponse(
            id=wl_id,
            name=clean_name,
            created_at=now_dt.isoformat(),
            updated_at=now_dt.isoformat(),
            tickers=[]
        )
    except Exception as ex:
        logger.error(f"Error creating watchlist: {ex}")
        raise HTTPException(status_code=500, detail=f"Failed to create watchlist: {ex}")


@router.delete("/{watchlist_id}", status_code=status.HTTP_200_OK)
def delete_watchlist(watchlist_id: str, current_user: str = Depends(get_current_user)):
    engine = get_engine()
    _ensure_tables(engine)

    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text("DELETE FROM quant_watchlist_tickers WHERE watchlist_id = :wid"),
                {"wid": watchlist_id}
            )
            res = conn.execute(
                sa.text("DELETE FROM quant_watchlists WHERE id = :wid"),
                {"wid": watchlist_id}
            )
            if res.rowcount == 0:
                raise HTTPException(status_code=404, detail="Watchlist not found.")
        return {"status": "deleted", "watchlist_id": watchlist_id}
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Error deleting watchlist {watchlist_id}: {ex}")
        raise HTTPException(status_code=500, detail=f"Failed to delete watchlist: {ex}")


@router.post("/{watchlist_id}/tickers", response_model=WatchlistTickerItem, status_code=status.HTTP_201_CREATED)
def add_ticker_to_watchlist(
    watchlist_id: str,
    req: AddTickerRequest,
    current_user: str = Depends(get_current_user)
):
    clean_ticker = req.ticker.strip().upper()
    if not clean_ticker:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty.")

    is_valid, indices = validate_ticker_in_indices(clean_ticker)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{clean_ticker}' is not a constituent of any major index (S&P 500, Nasdaq 100, Dow 30, Russell 2000, or major ETFs)."
        )

    engine = get_engine()
    _ensure_tables(engine)

    try:
        with engine.begin() as conn:
            wl_exists = conn.execute(
                sa.text("SELECT id FROM quant_watchlists WHERE id = :wid"),
                {"wid": watchlist_id}
            ).scalar()
            if not wl_exists:
                raise HTTPException(status_code=404, detail=f"Watchlist '{watchlist_id}' not found.")

            already_in = conn.execute(
                sa.text("SELECT ticker FROM quant_watchlist_tickers WHERE watchlist_id = :wid AND ticker = :sym"),
                {"wid": watchlist_id, "sym": clean_ticker}
            ).scalar()
            if already_in:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ticker '{clean_ticker}' is already in this watchlist."
                )

            now_dt = datetime.now(timezone.utc)
            indices_str = ",".join(indices)
            conn.execute(
                sa.text("""
                    INSERT INTO quant_watchlist_tickers (watchlist_id, ticker, indices, added_at)
                    VALUES (:wid, :sym, :ind, :now)
                """),
                {"wid": watchlist_id, "sym": clean_ticker, "ind": indices_str, "now": now_dt}
            )

            conn.execute(
                sa.text("UPDATE quant_watchlists SET updated_at = :now WHERE id = :wid"),
                {"wid": watchlist_id, "now": now_dt}
            )

        return WatchlistTickerItem(
            ticker=clean_ticker,
            indices=indices,
            added_at=now_dt.isoformat()
        )
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Error adding ticker {clean_ticker} to watchlist {watchlist_id}: {ex}")
        raise HTTPException(status_code=500, detail=f"Failed to add ticker: {ex}")


@router.delete("/{watchlist_id}/tickers/{ticker}", status_code=status.HTTP_200_OK)
def remove_ticker_from_watchlist(
    watchlist_id: str,
    ticker: str,
    current_user: str = Depends(get_current_user)
):
    clean_ticker = ticker.strip().upper()
    engine = get_engine()
    _ensure_tables(engine)

    try:
        with engine.begin() as conn:
            res = conn.execute(
                sa.text("DELETE FROM quant_watchlist_tickers WHERE watchlist_id = :wid AND ticker = :sym"),
                {"wid": watchlist_id, "sym": clean_ticker}
            )
            if res.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Ticker '{clean_ticker}' not found in watchlist.")

            now_dt = datetime.now(timezone.utc)
            conn.execute(
                sa.text("UPDATE quant_watchlists SET updated_at = :now WHERE id = :wid"),
                {"wid": watchlist_id, "now": now_dt}
            )

        return {"status": "deleted", "watchlist_id": watchlist_id, "ticker": clean_ticker}
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Error removing ticker {clean_ticker} from watchlist {watchlist_id}: {ex}")
        raise HTTPException(status_code=500, detail=f"Failed to remove ticker: {ex}")


@router.get("/{watchlist_id}/quotes", response_model=WatchlistQuotesResponse)
async def get_watchlist_quotes(
    watchlist_id: str,
    current_user: str = Depends(get_current_user)
):
    engine = get_engine()
    _ensure_tables(engine)

    try:
        with engine.connect() as conn:
            wl_exists = conn.execute(
                sa.text("SELECT id FROM quant_watchlists WHERE id = :wid"),
                {"wid": watchlist_id}
            ).scalar()
            if not wl_exists:
                raise HTTPException(status_code=404, detail=f"Watchlist '{watchlist_id}' not found.")

            rows = conn.execute(
                sa.text("SELECT ticker FROM quant_watchlist_tickers WHERE watchlist_id = :wid ORDER BY added_at ASC"),
                {"wid": watchlist_id}
            ).mappings().all()
            tickers = [r["ticker"] for r in rows]

        quotes_map = await get_batch_quotes(tickers)
        parsed_quotes = {k: QuoteItem(**v) for k, v in quotes_map.items()}

        return WatchlistQuotesResponse(
            watchlist_id=watchlist_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
            quotes=parsed_quotes
        )
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Error fetching quotes for watchlist {watchlist_id}: {ex}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch quotes: {ex}")
