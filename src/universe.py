"""
Ticker universe for the India screener: Nifty Midcap 150 + Nifty Smallcap 250.

NSE refuses downloads from many cloud servers (HTTP 403), GitHub Actions
included, so the list is taken from the first source that works:

    1. input/universe.csv         your own list, if the file exists
    2. NSE / Nifty Indices        three addresses tried per index, with a
                                  browser-like connection
    3. data/universe_snapshot.csv the saved copy of both index lists

Whenever the live download works, the saved copy is refreshed, and the
workflow commits it back to the repository. The indices are only rebalanced
twice a year, so a saved copy a few months old loses very little.

The index files carry an Industry column, which is used for the first round
of exclusions at no extra cost.
"""
from __future__ import annotations
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd

try:
    from curl_cffi import requests as http
    USE_CURL_CFFI = True
except ImportError:  # pragma: no cover
    import requests as http
    USE_CURL_CFFI = False

INDEX_FILES = {
    "Nifty Midcap 150": ("ind_niftymidcap150list.csv", 150),
    "Nifty Smallcap 250": ("ind_niftysmallcap250list.csv", 250),
}
SOURCES = [
    "https://nsearchives.nseindia.com/content/indices/{file}",
    "https://www.niftyindices.com/IndexConstituent/{file}",
    "https://archives.nseindia.com/content/indices/{file}",
]
CUSTOM_UNIVERSE = Path("input/universe.csv")
SNAPSHOT = Path("data/universe_snapshot.csv")
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
        if not ticker or ticker == "NAN" or ticker.startswith("DUMMY"):   # NSE lists placeholder rows during demergers
            continue
        out.append({
            "ticker": ticker,
            "name": _clean(r[name]) if name is not None and name != sym else "",
            "sector": _clean(r[industry]) if industry is not None else "",
            "industry": "",
        })
    return out


def _download(url: str) -> str | None:
    """Text of a URL, or None on any failure. Kept separate so tests can replace it."""
    try:
        if USE_CURL_CFFI:
            r = http.get(url, headers=HEADERS, timeout=20, impersonate="chrome120")
        else:
            r = http.get(url, headers=HEADERS, timeout=20)
        return r.text if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def _live_index(label: str) -> pd.DataFrame | None:
    """One index list from the first address that returns a real CSV."""
    filename, expected = INDEX_FILES[label]
    for template in SOURCES:
        url = template.format(file=filename)
        text = _download(url)
        if not text or "Symbol" not in text[:300]:
            continue
        try:
            df = pd.read_csv(StringIO(text))
        except Exception:  # noqa: BLE001
            continue
        if _find_col(df, "symbol") is not None and len(df) >= 0.8 * expected:
            print(f"  {label}: {len(df)} rows from {url.split('/')[2]}")
            return df
    return None


def _load_snapshot() -> pd.DataFrame | None:
    try:
        df = pd.read_csv(SNAPSHOT)
        return df if len(df) else None
    except (OSError, ValueError):
        return None


def _save_snapshot(frames: dict[str, pd.DataFrame]) -> None:
    parts = []
    for label, df in frames.items():
        cols = {"Company Name": _find_col(df, "company", "name"), "Industry": _find_col(df, "industry"),
                "Symbol": _find_col(df, "symbol")}
        part = pd.DataFrame({k: (df[v] if v is not None else "") for k, v in cols.items()})
        part.insert(0, "Index", label)
        parts.append(part)
    out = pd.concat(parts, ignore_index=True)
    out["As Of"] = date.today().isoformat()
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(SNAPSHOT, index=False)


def get_universe() -> tuple[list[dict], str]:
    """Returns (rows, description). Each row: ticker, name, sector (NSE industry group), industry."""
    if CUSTOM_UNIVERSE.exists():
        rows = _rows(pd.read_csv(CUSTOM_UNIVERSE))
        print(f"  custom universe {CUSTOM_UNIVERSE}: {len(rows)} tickers")
        return _dedupe(rows), f"custom list ({CUSTOM_UNIVERSE})"

    live = {label: _live_index(label) for label in INDEX_FILES}
    snapshot = _load_snapshot()
    if all(df is not None for df in live.values()):
        _save_snapshot(live)
        rows = [r for df in live.values() for r in _rows(df)]
        return _dedupe(rows), "Nifty Midcap 150 + Smallcap 250"

    rows, used_saved, as_of = [], [], ""
    for label, df in live.items():
        if df is not None:
            rows += _rows(df)
            continue
        if snapshot is not None and "Index" in snapshot.columns:
            part = snapshot[snapshot["Index"] == label]
            if len(part):
                rows += _rows(part.drop(columns=["Index"]))
                used_saved.append(label)
                as_of = _clean(part["As Of"].iloc[0]) if "As Of" in part.columns else ""
                print(f"  {label}: NSE refused the download, using the saved list ({len(part)} rows, {as_of})")
                continue
        print(f"  {label}: FAILED, no live download and no saved list")
    described = "Nifty Midcap 150 + Smallcap 250"
    if used_saved:
        described += f" (saved list of {as_of})" if as_of else " (saved list)"
    return _dedupe(rows), described


def _dedupe(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        if r["ticker"] not in seen:
            seen.add(r["ticker"])
            out.append(r)
    return sorted(out, key=lambda r: r["ticker"])


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
