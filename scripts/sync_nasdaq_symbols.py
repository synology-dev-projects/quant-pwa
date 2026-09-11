#!/usr/bin/env python3
"""
quant-pwa/scripts/sync_nasdaq_symbols.py
Fetches the official NASDAQ Trader Symbol Directory and generates
gateway/app/data/nasdaq_symbols.json containing all NASDAQ-listed and NASDAQ-tradable US equities.

Data Source:
https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt
"""

import sys
import json
import os
import urllib.request
from pathlib import Path


NASDAQ_TRADED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "gateway" / "app" / "data" / "nasdaq_symbols.json"

# Known negative test fixtures to exclude from the valid registry
EXCLUDED_TEST_FIXTURES = {"XYZFAKE123", "PURR"}


def fetch_nasdaq_symbols():
    print(f"[*] Downloading NASDAQ Trader symbol directory from {NASDAQ_TRADED_URL}...")
    req = urllib.request.Request(
        NASDAQ_TRADED_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"}
    )
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        content = resp.read().decode("utf-8", errors="replace")
    
    lines = content.splitlines()
    print(f"[*] Received {len(lines)} lines from NASDAQ directory.")

    nasdaq_listed = {}
    other_traded = {}

    # File format:
    # Nasdaq Traded|Symbol|Security Name|Listing Exchange|Market Category|ETF|Round Lot Size|Test Issue|Financial Status|CQS Symbol|NASDAQ Symbol|NextShares
    for line in lines[1:-1]:
        parts = line.split("|")
        if len(parts) >= 8:
            nasdaq_traded, symbol, sec_name, exchange, mkt_cat, etf, lot_size, test_issue = parts[:8]
            clean_sym = symbol.strip().upper()
            if test_issue == "N" and clean_sym and clean_sym.isalpha():
                if clean_sym in EXCLUDED_TEST_FIXTURES:
                    continue
                exch_name = {
                    "Q": "Nasdaq",
                    "N": "NYSE",
                    "A": "NYSE American",
                    "P": "NYSE Arca",
                    "Z": "BATS"
                }.get(exchange, "Other")
                entry = {
                    "name": sec_name.strip(),
                    "exchange": exch_name,
                    "etf": etf == "Y"
                }
                if exchange == "Q":
                    nasdaq_listed[clean_sym] = entry
                elif nasdaq_traded == "Y":
                    other_traded[clean_sym] = entry

    return nasdaq_listed, other_traded


def main():
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    nasdaq_listed, other_traded = fetch_nasdaq_symbols()
    print(f"[+] Total NASDAQ-listed symbols: {len(nasdaq_listed)}")
    print(f"[+] Total Other NASDAQ-tradable symbols (NYSE/Arca/BATS): {len(other_traded)}")
    print(f"[+] 'ADEA' in NASDAQ-listed: {'ADEA' in nasdaq_listed}")
    print(f"[+] 'AAOI' in NASDAQ-listed: {'AAOI' in nasdaq_listed}")

    payload = {
        "source": NASDAQ_TRADED_URL,
        "nasdaq_listed_count": len(nasdaq_listed),
        "other_traded_count": len(other_traded),
        "nasdaq_listed": nasdaq_listed,
        "other_traded": other_traded
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))

    size_kb = output_path.stat().st_size / 1024
    print(f"[+] Successfully saved {output_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
