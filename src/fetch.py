"""
Fundamentals fetch from screener.in.

Screener.in is India's most popular equity research site with rich fundamentals
that are much better suited to Indian markets than yfinance:
  * Promoter holding % and Pledged % (single most predictive negative signal
    in Indian small caps — high pledge often precedes stock collapses)
  * ROCE — the metric of choice for Indian analysts (better than ROA)
  * Multi-year CAGRs — pre-computed 3y, 5y, 10y compounded growth
  * Quarterly results with segment breakdown

No official API — we scrape the public company pages. Since we're doing
one page per company at a polite pace with browser-like headers, this
works reliably.

URLs:
  https://www.screener.in/company/{SYMBOL}/consolidated/   (preferred)
  https://www.screener.in/company/{SYMBOL}/                (fallback for standalone-only cos.)
"""
from __future__ import annotations
import re
import time
import warnings
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

BASE_URL = "https://www.screener.in/company"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.screener.in/",
    "Connection": "keep-alive",
}

FETCH_DELAY = 0.7  # seconds between scrapes — polite pacing, screener is generous but not unlimited


# ------------------------------------------------------------------ #
# Text parsing helpers
# ------------------------------------------------------------------ #

_NUM_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")


def _to_float(s: str | None) -> float | None:
    """Parse '₹ 1,234.56 Cr.' or '12.34 %' or '1,23,456' into a float."""
    if s is None:
        return None
    s = str(s).strip()
    if not s or s in ("-", "—", ""):
        return None
    m = _NUM_RE.search(s.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _text(el) -> str:
    """BeautifulSoup element → clean text."""
    return el.get_text(strip=True) if el else ""


# ------------------------------------------------------------------ #
# Section parsers
# ------------------------------------------------------------------ #

def _parse_top_ratios(soup: BeautifulSoup) -> dict[str, Any]:
    """
    Parse the top-right ratios box on a company page.

    Contains: Market Cap, Current Price, High/Low, Stock P/E, Book Value,
              Dividend Yield, ROCE, ROE, Face Value
    """
    out: dict[str, Any] = {}

    top = soup.find("ul", id="top-ratios") or soup.find("ul", class_="company-ratios")
    if not top:
        # Fallback: look for any ul with li>span.name pattern
        for ul in soup.find_all("ul"):
            if ul.find("span", class_="name"):
                top = ul
                break
    if not top:
        return out

    for li in top.find_all("li"):
        name_el = li.find("span", class_="name")
        val_el = li.find("span", class_="value") or li.find("span", class_="number")
        if not name_el:
            continue
        name = _text(name_el).lower()
        raw_val = _text(val_el) if val_el else _text(li)

        if "market cap" in name:
            out["market_cap_cr"] = _to_float(raw_val)
        elif "current price" in name:
            out["current_price"] = _to_float(raw_val)
        elif "high" in name and "low" in name:
            # "High / Low: 1,234 / 987"
            parts = raw_val.split("/")
            if len(parts) == 2:
                out["high_52w"] = _to_float(parts[0])
                out["low_52w"] = _to_float(parts[1])
        elif name.startswith("stock p/e") or name == "p/e":
            out["pe_ratio"] = _to_float(raw_val)
        elif "book value" in name:
            out["book_value"] = _to_float(raw_val)
        elif "dividend yield" in name:
            out["dividend_yield"] = _to_float(raw_val)
        elif name.startswith("roce"):
            out["roce"] = _to_float(raw_val)
        elif name.startswith("roe"):
            out["roe"] = _to_float(raw_val)
        elif "face value" in name:
            out["face_value"] = _to_float(raw_val)

    # Derived: price to book
    if out.get("current_price") and out.get("book_value") and out["book_value"] > 0:
        out["price_to_book"] = round(out["current_price"] / out["book_value"], 2)

    return out


def _parse_shareholding(soup: BeautifulSoup) -> dict[str, Any]:
    """
    Parse the Shareholding Pattern table. Grabs the MOST RECENT quarter's values
    for Promoters, FIIs, DIIs, Public, and (importantly) Pledged percentage.
    """
    out: dict[str, Any] = {}

    section = soup.find("section", id="shareholding")
    if not section:
        return out

    # Grab all quarterly-shareholding tables (there may be two: quarterly + yearly)
    tables = section.find_all("table")
    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = _text(cells[0]).lower()
            # Last data cell is the most recent quarter
            last_val = _text(cells[-1])
            v = _to_float(last_val)
            if v is None:
                continue
            if label.startswith("promoter"):
                out["promoter_holding"] = v
            elif "pledg" in label:
                out["promoter_pledge"] = v
            elif label.startswith("fii"):
                out["fii_holding"] = v
            elif label.startswith("dii"):
                out["dii_holding"] = v
            elif label.startswith("public"):
                out["public_holding"] = v
            elif "government" in label:
                out["government_holding"] = v

    return out


def _parse_growth_rates(soup: BeautifulSoup) -> dict[str, Any]:
    """
    Parse the 'Compounded Sales Growth' and 'Compounded Profit Growth' tables.

    These sit in the Analysis section. Each has rows like:
      10 Years:  18%
      5 Years:   22%
      3 Years:   15%
      TTM:       28%
    """
    out: dict[str, Any] = {}

    # Look for tables inside the ratios/growth area
    # Structure: <table><tr><td>Compounded Sales Growth</td></tr>...<tr><td>5 Years:</td><td>22%</td></tr></table>
    for table in soup.find_all("table", class_="ranges-table"):
        header = _text(table.find("th") or table.find("td")).lower()
        if "sales" in header or "revenue" in header:
            prefix = "sales_growth"
        elif "profit" in header:
            prefix = "profit_growth"
        elif "stock" in header and "price" in header:
            prefix = "price_cagr"
        elif "roe" in header:
            prefix = "roe_hist"
        else:
            continue

        for row in table.find_all("tr")[1:]:  # skip header row
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label = _text(cells[0]).lower()
            val = _to_float(_text(cells[1]))
            if val is None:
                continue
            if "10 year" in label:
                out[f"{prefix}_10y"] = val
            elif "5 year" in label:
                out[f"{prefix}_5y"] = val
            elif "3 year" in label:
                out[f"{prefix}_3y"] = val
            elif "ttm" in label:
                out[f"{prefix}_ttm"] = val

    return out


def _parse_pl_ratios(soup: BeautifulSoup) -> dict[str, Any]:
    """
    Pull OPM (Operating Profit Margin) and debt/equity from tables.
    OPM is in the Profit & Loss table, D/E in the Ratios table.
    """
    out: dict[str, Any] = {}

    for section_id in ["profit-loss", "ratios", "balance-sheet"]:
        section = soup.find("section", id=section_id)
        if not section:
            continue
        for row in section.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = _text(cells[0]).lower().strip()
            # Take the most recent (last) column value
            last_val = _text(cells[-1])
            v = _to_float(last_val)
            if v is None:
                continue
            if label == "opm %" or "operating profit margin" in label:
                out["operating_margin"] = v
            elif label == "npm %" or "net profit margin" in label:
                out["profit_margin"] = v
            elif label == "debt / equity" or label == "debt to equity":
                out["debt_to_equity"] = v
            elif label == "roce %":
                # Latest year ROCE (top-ratios has 3y avg; this is current)
                out["roce_latest"] = v
            elif label == "roe %":
                out["roe_latest"] = v

    return out


# ------------------------------------------------------------------ #
# Main per-ticker scraper
# ------------------------------------------------------------------ #

def _fetch_html(symbol: str, retries: int = 1) -> tuple[str | None, str]:
    """Try consolidated URL first, then standalone. Returns (html, error)."""
    last_err = "unknown"
    for suffix in ("consolidated/", ""):
        url = f"{BASE_URL}/{symbol}/{suffix}"
        for attempt in range(retries + 1):
            try:
                r = requests.get(url, headers=BROWSER_HEADERS, timeout=25)
                if r.status_code == 200:
                    return r.text, ""
                if r.status_code == 404:
                    last_err = f"404 (page not found for {suffix or 'standalone'})"
                    break  # try next suffix
                if r.status_code == 429:
                    last_err = f"429 rate limited"
                    if attempt < retries:
                        time.sleep(10)
                        continue
                last_err = f"HTTP {r.status_code}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:80]}"
                if attempt < retries:
                    time.sleep(2)
                    continue
    return None, last_err


def scrape_screener(symbol: str) -> dict[str, Any]:
    """
    Scrape screener.in for one company. Returns a dict with all fields
    we could extract, plus 'symbol' and 'error' (None on success).
    """
    result: dict[str, Any] = {"symbol": symbol, "error": None}

    html, err = _fetch_html(symbol)
    if html is None:
        result["error"] = err
        return result

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        result["error"] = f"parse: {type(e).__name__}: {e}"
        return result

    # Company name (used for display)
    h1 = soup.find("h1")
    if h1:
        result["name"] = _text(h1)

    # Sector / industry — screener has this in a breadcrumb-like element
    company_info = soup.find("p", class_="sub")
    if company_info:
        result["sector"] = _text(company_info)

    # Merge all section parsers
    try:
        result.update(_parse_top_ratios(soup))
    except Exception as e:
        result["ratios_parse_error"] = f"{type(e).__name__}: {e}"

    try:
        result.update(_parse_shareholding(soup))
    except Exception as e:
        result["shareholding_parse_error"] = f"{type(e).__name__}: {e}"

    try:
        result.update(_parse_growth_rates(soup))
    except Exception as e:
        result["growth_parse_error"] = f"{type(e).__name__}: {e}"

    try:
        result.update(_parse_pl_ratios(soup))
    except Exception as e:
        result["pl_parse_error"] = f"{type(e).__name__}: {e}"

    # Sanity check: did we get anything useful?
    if not result.get("market_cap_cr") and not result.get("pe_ratio"):
        result["error"] = "no core fields extracted (page structure may have changed)"

    return result


def fetch_fundamentals(tickers: list[str], **_kwargs) -> pd.DataFrame:
    """
    Scrape screener.in for a list of tickers sequentially with polite delays.

    Sequential (not parallel) — same reason as US technicals: screener may
    rate-limit or IP-ban aggressive scrapers. ~0.7s/ticker means 400 tickers
    in ~5 min. Acceptable.
    """
    n = len(tickers)
    print(f"Scraping screener.in for {n} tickers (sequential, {FETCH_DELAY}s delay)")

    results: list[dict[str, Any]] = []
    t0 = time.time()

    for i, ticker in enumerate(tickers, 1):
        row = scrape_screener(ticker)
        results.append(row)

        if i % 25 == 0 or i == n:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed else 0
            eta = (n - i) / rate if rate else 0
            n_ok_so_far = sum(1 for r in results if r["error"] is None)
            print(f"  {i}/{n} · ok={n_ok_so_far} · {elapsed:.0f}s · ETA {eta:.0f}s")

        if i < n:
            time.sleep(FETCH_DELAY)

    df = pd.DataFrame(results)
    n_ok = df["error"].isna().sum()
    print(f"\nFundamentals success: {n_ok}/{n} ({n_ok/n*100:.0f}%)")

    if n_ok < n * 0.7:
        errs = df[df["error"].notna()]["error"]
        print("Top error types:")
        for err, count in errs.value_counts().head(3).items():
            print(f"  ({count}x) {err[:140]}")

    return df
