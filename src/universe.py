"""
Ticker universe for the India screener.

Default: Nifty Midcap 150 + Nifty Smallcap 250 (about 400 stocks), from the
constituent CSV files NSE publishes. Those files carry an Industry column,
which is used for the first round of exclusions at no extra cost.

Optional: put your own list in input/universe.csv and it is used instead.
The first column must hold NSE symbols (without .NS). Columns named
name / industry are used if present.
"""
from __future__ import annotations
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

NSE_INDEX_URLS = {
    "Nifty Midcap 150": "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "Nifty Smallcap 250": "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
}
CUSTOM_UNIVERSE = Path("input/universe.csv")
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/121.0.0.0 Safari/537.36"),
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _clean(value) -> str:
    return "" if value is None or (isinstance(value, float) and value != value) else str(value).strip()


def _find_col(df: pd.DataFrame, *needles: str):
    for col in df.columns:
        low = str(col).lower()
        if any(n in low for n in needles):
            return col
    return None


def _rows(df: pd.DataFrame) -> list[dict]:
    sym = _find_col(df, "symbol", "ticker")
    if sym is None:
        sym = df.columns[0]
    name, industry = _find_col(df, "company", "name"), _find_col(df, "industry", "sector")
    out = []
    for _, r in df.iterrows():
        ticker = _clean(r[sym]).upper().replace(".NS", "")
        if not ticker or ticker == "NAN":
            continue
        out.append({
            "ticker": ticker,
            "name": _clean(r[name]) if name is not None and name != sym else "",
            "sector": _clean(r[industry]) if industry is not None else "",
            "industry": "",
        })
    return out


def _from_nse() -> list[dict]:
    rows: dict[str, dict] = {}
    for label, url in NSE_INDEX_URLS.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            found = _rows(pd.read_csv(StringIO(resp.text)))
            for r in found:
                rows.setdefault(r["ticker"], r)
            print(f"  {label}: {len(found)} tickers")
        except Exception as e:  # noqa: BLE001
            print(f"  {label}: FAILED ({type(e).__name__}: {e})")
    return sorted(rows.values(), key=lambda r: r["ticker"])


def get_universe() -> tuple[list[dict], str]:
    """Returns (rows, description). Each row: ticker, name, sector (NSE industry group), industry."""
    if CUSTOM_UNIVERSE.exists():
        rows = _rows(pd.read_csv(CUSTOM_UNIVERSE))
        seen, out = set(), []
        for r in rows:
            if r["ticker"] not in seen:
                seen.add(r["ticker"])
                out.append(r)
        print(f"  custom universe {CUSTOM_UNIVERSE}: {len(out)} tickers")
        return out, f"custom list ({CUSTOM_UNIVERSE})"
    return _from_nse(), "Nifty Midcap 150 + Smallcap 250"


def exclusion_reason(sector: str, industry: str, cfg) -> str | None:
    """Why a company is outside the checklist's scope, or None if it is in scope."""
    s = (sector or "").strip().lower()
    for bad in cfg.EXCLUDED_INDUSTRIES:
        if s and s == bad.lower():
            return f"industry group: {sector}"
    text = f"{sector or ''} {industry or ''}".lower()
    for kw in cfg.EXCLUDED_INDUSTRY_KEYWORDS:
        if kw in text:
            return f"industry: {(industry or sector).strip()}"
    return None


SAMPLE = [
    {"ticker": t, "name": "", "sector": "", "industry": ""}
    for t in ["ASTRAL", "PERSISTENT", "COFORGE", "DIXON", "POLYCAB", "PIIND", "SUPREMEIND", "CUMMINSIND",
              "KPITTECH", "APLAPOLLO", "KEI", "GRINDWELL"]
]
