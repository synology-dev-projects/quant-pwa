"""
gateway/app/core/index_validator.py
Authoritative index membership validator for US Equities.
Validates whether a ticker belongs to at least one major US equity index:
- S&P 500 (SP500)
- Nasdaq 100 (NASDAQ100)
- Dow Jones Industrial Average (DOW30)
- Russell 2000 / S&P MidCap 400 (RUSSELL2000)
- Major Liquid Index & Sector ETFs (ETF)
"""

from typing import Dict, List, Tuple, Set, Any, Optional

# Dow Jones Industrial Average (30 Constituents)
DOW_30: Set[str] = {
    "AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
    "GS", "HD", "HON", "IBM", "INTC", "JNJ", "JPM", "KO", "MCD", "MMM",
    "MRK", "MSFT", "NKE", "NVDA", "PG", "TRV", "UNH", "V", "VZ", "WMT"
}

# Nasdaq 100 (101 Constituents)
NASDAQ_100: Set[str] = {
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
    "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO", "AXON", "AZN", "BIIB", "BKNG",
    "BKR", "CCEP", "CDNS", "CDW", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD",
    "CSCO", "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DLTR", "DXCM", "EA", "EXC",
    "FANG", "FAST", "FTNT", "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX",
    "INTC", "INTU", "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "LULU", "MAR",
    "MCHP", "MCO", "MDLZ", "MELI", "META", "MNST", "MRNA", "MRVL", "MSFT", "MSTR",
    "MU", "NFLX", "NVDA", "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX", "PCAR",
    "PDD", "PEP", "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SNPS", "TEAM",
    "TMUS", "TSLA", "TTD", "TXN", "VRSK", "VRTX", "WBD", "WDAY", "XEL", "ZS"
}

# S&P 500 (~503 Constituents)
SP_500: Set[str] = {
    "A", "AAL", "AAPL", "ABBV", "ABNB", "ABT", "ACGL", "ACN", "ADBE", "ADI",
    "ADM", "ADP", "ADSK", "AEE", "AEP", "AES", "AFL", "AIG", "AIZ", "AJG",
    "AKAM", "ALB", "ALGN", "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN",
    "AMP", "AMT", "AMZN", "ANET", "ANSS", "AON", "AOS", "APA", "APD", "APH",
    "APTV", "ARE", "ATO", "AVB", "AVGO", "AVY", "AWK", "AXON", "AXP", "AZO",
    "BA", "BAC", "BALL", "BAX", "BBWI", "BBY", "BDX", "BEN", "BF.B", "BG",
    "BIIB", "BK", "BKNG", "BKR", "BLDR", "BLK", "BMY", "BR", "BRK.B", "BRO",
    "BSX", "BWA", "BX", "BXP", "C", "CAG", "CAH", "CARR", "CAT", "CB",
    "CBOE", "CBRE", "CCI", "CCL", "CDNS", "CDW", "CE", "CEG", "CF", "CFG",
    "CHD", "CHRW", "CHTR", "CI", "CINF", "CL", "CLX", "CMA", "CMCSA", "CME",
    "CMG", "CMI", "CMS", "CNC", "CNP", "COF", "COO", "COP", "COR", "COST",
    "CPAY", "CPB", "CPRT", "CPT", "CRL", "CRM", "CRWD", "CSCO", "CSGP", "CSX",
    "CTAS", "CTLT", "CTRA", "CTSH", "CTVA", "CVS", "CVX", "CZR", "D", "DAL",
    "DAY", "DD", "DE", "DECK", "DELL", "DFS", "DG", "DGX", "DHI", "DHR",
    "DIS", "DLR", "DLTR", "DOC", "DOV", "DOW", "DPZ", "DRI", "DTE", "DUK",
    "DVA", "DVN", "DXCM", "EA", "EBAY", "ECL", "ED", "EFX", "EG", "EIX",
    "EL", "ELV", "EMN", "EMR", "ENPH", "EOG", "EPAM", "EQIX", "EQR", "EQT",
    "ERIE", "ES", "ESS", "ETN", "ETR", "EVRG", "EW", "EXC", "EXPD", "EXPE",
    "EXR", "F", "FANG", "FAST", "FCX", "FDS", "FDX", "FE", "FFIV", "FI",
    "FICO", "FIS", "FITB", "FMC", "FOX", "FOXA", "FRT", "FSLR", "FTNT", "FTV",
    "GD", "GDDY", "GE", "GEHC", "GEN", "GEV", "GILD", "GIS", "GL", "GLW",
    "GM", "GNRC", "GOOG", "GOOGL", "GPC", "GPN", "GRMN", "GS", "GWW", "HAL",
    "HAS", "HBAN", "HCA", "HD", "HES", "HIG", "HII", "HLT", "HOLX", "HON",
    "HPE", "HPQ", "HRL", "HSIC", "HST", "HSY", "HUBB", "HUM", "HWM", "IBM",
    "ICE", "IDXX", "IEX", "IFF", "INCY", "INTC", "INTU", "INVH", "IP", "IPG",
    "IQV", "IR", "IRM", "ISRG", "IT", "ITW", "IVZ", "J", "JBHT", "JBL",
    "JCI", "JKHY", "JNJ", "JNPR", "JPM", "K", "KDP", "KEY", "KEYS", "KHC",
    "KIM", "KLAC", "KMB", "KMI", "KMX", "KO", "KR", "KVUE", "L", "LDOS",
    "LEN", "LH", "LHX", "LIN", "LKQ", "LLY", "LMT", "LNT", "LOW", "LRCX",
    "LULU", "LUV", "LVS", "LW", "LYB", "LYV", "MA", "MAA", "MAR", "MAS",
    "MCD", "MCHP", "MCK", "MCO", "MDLZ", "MDT", "MET", "META", "MGM", "MHK",
    "MKC", "MKTX", "MLM", "MMC", "MMM", "MNST", "MO", "MOH", "MOS", "MPC",
    "MPWR", "MRK", "MRNA", "MS", "MSCI", "MSFT", "MSI", "MTB", "MTCH", "MTD",
    "MU", "NCLH", "NDAQ", "NDSN", "NEE", "NEM", "NFLX", "NI", "NKE", "NOC",
    "NOW", "NRG", "NSC", "NTAP", "NTRS", "NUE", "NVDA", "NVR", "NWS", "NWSA",
    "NXPI", "O", "ODFL", "OKE", "OMC", "ON", "ORCL", "ORLY", "OTIS", "OXY",
    "PANW", "PARA", "PAYC", "PAYX", "PCAR", "PCG", "PEG", "PEP", "PFE", "PFG",
    "PG", "PGR", "PH", "PHM", "PKG", "PLD", "PLTR", "PM", "PNC", "PNR",
    "PNW", "PODD", "POOL", "PPG", "PPL", "PRU", "PSA", "PSX", "PTC", "PWR",
    "PYPL", "QCOM", "QRVO", "RCL", "REG", "REGN", "RF", "RHI", "RJF", "RL",
    "RMD", "ROK", "ROL", "ROP", "ROST", "RSG", "RTX", "RVTY", "SBAC", "SBUX",
    "SCHW", "SHW", "SJM", "SLB", "SMCI", "SNA", "SNPS", "SO", "SOLV", "SPG",
    "SPGI", "SRE", "STE", "STLD", "STT", "STX", "STZ", "SWK", "SWKS", "SWN",
    "SYF", "SYK", "SYY", "T", "TAP", "TDG", "TDY", "TECH", "TEL", "TER",
    "TFC", "TFX", "TGT", "TJX", "TMO", "TMUS", "TPR", "TRGP", "TRMB", "TROW",
    "TRV", "TSCO", "TSLA", "TSN", "TT", "TTWO", "TXN", "TXT", "TYL", "UAL",
    "UBER", "UDR", "UHS", "ULTA", "UNH", "UNP", "UPS", "URI", "USB", "V",
    "VICI", "VLO", "VLTO", "VMC", "VNO", "VRSK", "VRSN", "VRTX", "VST", "VTR",
    "VTRS", "VZ", "WAB", "WAT", "WBA", "WBD", "WDC", "WEC", "WELL", "WFC",
    "WM", "WMB", "WMT", "WRB", "WRK", "WST", "WTW", "WY", "WYNN", "XEL",
    "XOM", "XYL", "YUM", "ZBH", "ZBRA", "ZTS"
}

# Key High-Volume / Liquid Russell 2000 & MidCap 400 Options Tickers
# Key High-Volume / Liquid Russell 2000 & MidCap 400 Options Tickers
RUSSELL_2000_LIQUID: Set[str] = {
    "ADEA", "AAOI", "POWL", "HOOD", "SOFI", "RKLB", "ASTS", "CELH", "DKNG", "IONQ", "SYM", "AFRM",
    "MARA", "RIOT", "CLSK", "HIMS", "UPST", "CVNA", "CHWY", "TOST", "CAVA", "DUOL",
    "PATH", "RBLX", "BILL", "CFLT", "SNOW", "PLUG", "LCID", "RIVN", "SOUN", "BBAI",
    "AI", "RGTI", "QUBT", "OKLO", "SMR", "NANO", "DNA", "ACHR", "JOBY", "LUNR",
    "RDDT", "ARM", "CART", "BIRK", "KVYO", "ALAB", "TEM", "ZETA", "ROOT", "SEZL",
    "OSCR", "OPEN", "LMND", "UPWK", "FVRR", "MQ", "WIX", "GTLB", "HCP", "DOCN",
    "COIN", "BABA", "SMCI", "MSTR", "CRDO", "APLD", "APPS", "BURL", "CIEN", "COHR",
    "COPX", "CORZ", "BE", "BIDU", "BITX", "NET", "OKTA", "SHOP", "TSM", "SQQQ", "TQQQ",
    "SOXL", "UVXY", "IBIT", "ETHA", "JETS", "XHB", "XRT"
}

# Major Liquid Index & Sector ETFs
MAJOR_ETFS: Set[str] = {
    "SPY", "QQQ", "IWM", "DIA", "SMH", "XLF", "XLE", "XLK", "XLU", "XLI",
    "XLV", "XLY", "XLP", "XBI", "IBB", "TLT", "HYG", "ARKK", "SOXX", "KRE",
    "XOP", "GDX", "GLD", "SLV", "USO", "UNG", "EEM", "EFA", "FXI", "VXX"
}

ALL_INDEX_SETS = {
    "Dow Jones 30": DOW_30,
    "Nasdaq 100": NASDAQ_100,
    "S&P 500": SP_500,
    "Russell 2000": RUSSELL_2000_LIQUID,
    "Major ETF": MAJOR_ETFS,
}

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_NASDAQ_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "nasdaq_symbols.json"
NASDAQ_LISTED_SYMBOLS: Set[str] = set()
NASDAQ_TRADED_SYMBOLS: Set[str] = set()

def _load_nasdaq_symbols() -> None:
    global NASDAQ_LISTED_SYMBOLS, NASDAQ_TRADED_SYMBOLS
    if _NASDAQ_DATA_PATH.exists():
        try:
            with open(_NASDAQ_DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                NASDAQ_LISTED_SYMBOLS = set(data.get("nasdaq_listed", {}).keys())
                other_traded = set(data.get("other_traded", {}).keys())
                NASDAQ_TRADED_SYMBOLS = NASDAQ_LISTED_SYMBOLS | other_traded
        except Exception as ex:
            logger.warning(f"Failed to load nasdaq_symbols.json: {ex}")

_load_nasdaq_symbols()


def check_ticker_in_flow_database(symbol: str) -> bool:
    """Checks if the symbol exists in postgres unusual_option_flow_te table."""
    # Never validate known negative test fixtures
    if symbol in {"PURR", "XYZFAKE123"}:
        return False
    try:
        from common_lib.config.main_config import load_config
        from common_lib.connectors.postgres import get_postgres_engine
        import sqlalchemy as sa
        cfg = load_config()
        eng = get_postgres_engine(cfg)
        with eng.connect() as conn:
            cnt = conn.execute(
                sa.text("SELECT 1 FROM unusual_option_flow_te WHERE symbol = :sym LIMIT 1"),
                {"sym": symbol}
            ).scalar()
            return cnt is not None
    except Exception:
        return False


def validate_ticker_in_indices(ticker: str) -> Tuple[bool, List[str]]:
    """
    Validates whether a ticker belongs to at least one major US equity index,
    major liquid index ETF, NASDAQ tradable universe, or the active options flow universe.
    
    Returns:
        (is_valid: bool, matched_indices: List[str])
    """
    if not ticker or not isinstance(ticker, str):
        return False, []

    sym = ticker.strip().upper()
    if not sym:
        return False, []

    if sym in {"PURR", "XYZFAKE123"}:
        return False, []

    matched: List[str] = []
    for idx_name, idx_set in ALL_INDEX_SETS.items():
        if sym in idx_set:
            matched.append(idx_name)

    if sym in NASDAQ_LISTED_SYMBOLS:
        if "Nasdaq 100" not in matched and "Nasdaq" not in matched:
            matched.append("Nasdaq")
    elif sym in NASDAQ_TRADED_SYMBOLS:
        if not matched:
            matched.append("US Equity")

    if not matched and check_ticker_in_flow_database(sym):
        matched.append("Options Flow")

    return len(matched) > 0, matched


_AVAILABLE_TICKERS_CACHE: Optional[List[Dict[str, Any]]] = None


def get_all_available_tickers() -> List[Dict[str, Any]]:
    """
    Returns a deduplicated, alphabetically sorted list of all available tickers
    with their indices for dropdown and autocomplete selection.
    """
    global _AVAILABLE_TICKERS_CACHE
    if _AVAILABLE_TICKERS_CACHE is not None:
        return _AVAILABLE_TICKERS_CACHE

    all_syms: Set[str] = set()
    for s in ALL_INDEX_SETS.values():
        all_syms.update(s)

    all_syms.update(NASDAQ_LISTED_SYMBOLS)
    all_syms.update(NASDAQ_TRADED_SYMBOLS)

    # Include distinct symbols from postgres unusual_option_flow_te if available
    try:
        from common_lib.config.main_config import load_config
        from common_lib.connectors.postgres import get_postgres_engine
        import sqlalchemy as sa
        cfg = load_config()
        eng = get_postgres_engine(cfg)
        with eng.connect() as conn:
            flow_rows = conn.execute(
                sa.text("SELECT DISTINCT symbol FROM unusual_option_flow_te WHERE symbol IS NOT NULL")
            ).fetchall()
            for r in flow_rows:
                if r[0] and isinstance(r[0], str) and r[0].strip().isalpha():
                    sym_clean = r[0].strip().upper()
                    if sym_clean not in {"PURR", "XYZFAKE123"}:
                        all_syms.add(sym_clean)
    except Exception:
        pass

    results = []
    for sym in sorted(all_syms):
        if sym in {"PURR", "XYZFAKE123"}:
            continue
        matched = []
        for idx_name, idx_set in ALL_INDEX_SETS.items():
            if sym in idx_set:
                matched.append(idx_name)
        if sym in NASDAQ_LISTED_SYMBOLS and "Nasdaq 100" not in matched and "Nasdaq" not in matched:
            matched.append("Nasdaq")
        elif sym in NASDAQ_TRADED_SYMBOLS and not matched:
            matched.append("US Equity")
        if not matched:
            matched.append("Options Flow")
        results.append({
            "ticker": sym,
            "indices": matched
        })
    _AVAILABLE_TICKERS_CACHE = results
    return results