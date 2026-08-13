"""
Ticker universe: Nifty Midcap 150 + Nifty Smallcap 250 = ~400 NSE tickers.

Downloaded from NSE's public archives (free CSV downloads, no auth).
This is the natural "multibagger hunting ground" for Indian equities:
mid-caps roughly ₹20-80k Cr and small-caps below that. Excludes Nifty 50
(large caps too big to plausibly 10x) and micro-caps (too noisy).
"""
from __future__ import annotations
from io import StringIO

import pandas as pd
import requests

NSE_INDEX_URLS = {
    "midcap150":  "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "smallcap250": "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
}

# NSE occasionally blocks direct downloads without browser headers
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _fetch_nse_csv(url: str) -> pd.DataFrame:
    """Fetch a CSV from NSE archives with proper headers."""
    r = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text))


def get_universe(include_midcap: bool = True, include_smallcap: bool = True) -> list[str]:
    """
    Return the ticker universe for the India screener.

    Default: both Midcap 150 + Smallcap 250 = ~400 tickers.
    Symbols returned WITHOUT `.NS` suffix (added later by yfinance layer).
    Set include_midcap=False or include_smallcap=False to narrow.
    """
    if not include_midcap and not include_smallcap:
        raise ValueError("Must include at least one index (midcap or smallcap)")

    all_tickers: set[str] = set()
    if include_midcap:
        try:
            df = _fetch_nse_csv(NSE_INDEX_URLS["midcap150"])
            syms = df["Symbol"].astype(str).str.strip().tolist()
            all_tickers.update(syms)
            print(f"  Nifty Midcap 150: {len(syms)} tickers")
        except Exception as e:
            print(f"  Nifty Midcap 150: FAILED — {e}")
    if include_smallcap:
        try:
            df = _fetch_nse_csv(NSE_INDEX_URLS["smallcap250"])
            syms = df["Symbol"].astype(str).str.strip().tolist()
            all_tickers.update(syms)
            print(f"  Nifty Smallcap 250: {len(syms)} tickers")
        except Exception as e:
            print(f"  Nifty Smallcap 250: FAILED — {e}")
    return sorted(all_tickers)


def get_sample_tickers() -> list[str]:
    """A small hand-picked set of well-known mid/small caps for smoke tests."""
    return [
        "TATAMOTORS", "BAJAJHLDNG", "GODREJCP", "PIIND", "DIXON",
        "ASTRAL", "PERSISTENT", "COFORGE", "MPHASIS", "LICHSGFIN",
        "CUMMINSIND", "GLENMARK", "OBEROIRLTY", "POLYCAB", "AUBANK",
        "IDFCFIRSTB", "SUPREMEIND", "BALKRISIND", "ABFRL", "RAMCOCEM",
    ]


if __name__ == "__main__":
    tickers = get_universe()
    print(f"\nTotal unique tickers: {len(tickers)}")
    print(f"First 20: {tickers[:20]}")
