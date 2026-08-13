"""
Fundamentals fetch from screener.in.

Uses curl_cffi (already a yfinance dependency) which impersonates a real
Chrome browser at the TLS handshake level. Plain `requests` gets blocked
by screener.in's bot detection from cloud IPs (like GitHub Actions runners)
because its TLS fingerprint is obviously a Python library.

Falls back to standard `requests` if curl_cffi isn't available.

Uses a persistent Session that visits the homepage first to collect any
anti-bot cookies before hitting company pages.

If everything still fails, saves the first blocked response HTML to
output/debug_response.html so you can see exactly what screener returned.
"""
from __future__ import annotations
import re
import time
import warnings
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

# Try curl_cffi first (browser TLS fingerprint impersonation).
# Falls back to requests if not installed.
try:
    from curl_cffi import requests as http
    USE_CURL_CFFI = True
    IMPERSONATE = "chrome120"
except ImportError:
    import requests as http
    USE_CURL_CFFI = False
    IMPERSONATE = None

BASE_URL = "https://www.screener.in/company"
HOMEPAGE_URL = "https://www.screener.in/"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

FETCH_DELAY = 0.7

# Track diagnostic state so we can save the first blocked response for debugging
_DEBUG_SAVED = [False]
_DEBUG_PATH = Path("output/debug_response.html")


# ------------------------------------------------------------------ #
# Session with warm-up
# ------------------------------------------------------------------ #

def _make_session():
    """Create session, impersonate a browser if possible, warm up with homepage."""
    if USE_CURL_CFFI:
        s = http.Session(impersonate=IMPERSONATE)
    else:
        s = http.Session()
    s.headers.update(BROWSER_HEADERS)

    # Warm-up: hit homepage to collect any cookies (anti-bot, csrf, etc.)
    try:
        r = s.get(HOMEPAGE_URL, timeout=20)
        if USE_CURL_CFFI:
            print(f"  [fetch] curl_cffi session warmed up (impersonating {IMPERSONATE}), "
                  f"homepage returned HTTP {r.status_code}")
        else:
            print(f"  [fetch] plain requests session (curl_cffi not available), "
                  f"homepage returned HTTP {r.status_code}")
    except Exception as e:
        print(f"  [fetch] session warm-up failed: {e} — proceeding anyway")
    return s


# ------------------------------------------------------------------ #
# Text parsing helpers
# ------------------------------------------------------------------ #

_NUM_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")


def _to_float(s: str | None) -> float | None:
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
    return el.get_text(strip=True) if el else ""


# ------------------------------------------------------------------ #
# Section parsers (same as before, unchanged)
# ------------------------------------------------------------------ #

def _parse_top_ratios(soup: BeautifulSoup) -> dict[str, Any]:
    out: dict[str, Any] = {}

    top = soup.find("ul", id="top-ratios") or soup.find("ul", class_="company-ratios")
    if not top:
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

    if out.get("current_price") and out.get("book_value") and out["book_value"] > 0:
        out["price_to_book"] = round(out["current_price"] / out["book_value"], 2)

    return out


def _parse_shareholding(soup: BeautifulSoup) -> dict[str, Any]:
    out: dict[str, Any] = {}

    section = soup.find("section", id="shareholding")
    if not section:
        return out

    tables = section.find_all("table")
    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = _text(cells[0]).lower()
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
    out: dict[str, Any] = {}
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

        for row in table.find_all("tr")[1:]:
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
                out["roce_latest"] = v
            elif label == "roe %":
                out["roe_latest"] = v
    return out


# ------------------------------------------------------------------ #
# Per-ticker scraper (uses shared session)
# ------------------------------------------------------------------ #

def _save_debug_response(html: str, symbol: str, reason: str):
    """Save the first blocked/failed response so we can inspect what screener returned."""
    if _DEBUG_SAVED[0]:
        return
    try:
        _DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"<!-- DEBUG: response for {symbol} was rejected ({reason})\n"
            f"     saved for inspection. If this is a Cloudflare/bot challenge page,\n"
            f"     screener.in is blocking this runner's IP. -->\n"
        )
        _DEBUG_PATH.write_text(header + html[:20000], encoding="utf-8")
        _DEBUG_SAVED[0] = True
        print(f"  [fetch] saved first failed response to {_DEBUG_PATH}")
    except Exception:
        pass


def _fetch_html(session, symbol: str, retries: int = 1) -> tuple[str | None, str]:
    """Try consolidated URL first, then standalone."""
    last_err = "unknown"
    for suffix in ("consolidated/", ""):
        url = f"{BASE_URL}/{symbol}/{suffix}"
        for attempt in range(retries + 1):
            try:
                if USE_CURL_CFFI:
                    r = session.get(url, timeout=25, impersonate=IMPERSONATE)
                else:
                    r = session.get(url, timeout=25)
                if r.status_code == 200:
                    text = r.text
                    # Check if the response is actually a company page vs a challenge/error page
                    if "top-ratios" not in text and "company-ratios" not in text and "shareholding" not in text.lower():
                        preview = text[:300].replace("\n", " ")
                        last_err = f"HTTP 200 but not a company page (likely blocked). Snippet: {preview}"
                        _save_debug_response(text, symbol, "no company-page markers found")
                        break  # try next suffix
                    return text, ""
                if r.status_code == 404:
                    last_err = f"404 (page not found for {suffix or 'standalone'})"
                    break
                if r.status_code == 429:
                    last_err = "429 rate limited"
                    if attempt < retries:
                        time.sleep(10)
                        continue
                if r.status_code in (403, 503):
                    preview = r.text[:200].replace("\n", " ")
                    last_err = f"HTTP {r.status_code} (blocked). Snippet: {preview}"
                    _save_debug_response(r.text, symbol, f"HTTP {r.status_code}")
                    break
                last_err = f"HTTP {r.status_code}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:80]}"
                if attempt < retries:
                    time.sleep(2)
                    continue
    return None, last_err


def scrape_screener(session, symbol: str) -> dict[str, Any]:
    """Scrape screener.in for one company using shared session."""
    result: dict[str, Any] = {"symbol": symbol, "error": None}

    html, err = _fetch_html(session, symbol)
    if html is None:
        result["error"] = err
        return result

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        result["error"] = f"parse: {type(e).__name__}: {e}"
        return result

    h1 = soup.find("h1")
    if h1:
        result["name"] = _text(h1)

    company_info = soup.find("p", class_="sub")
    if company_info:
        result["sector"] = _text(company_info)

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

    if not result.get("market_cap_cr") and not result.get("pe_ratio"):
        result["error"] = "no core fields extracted (page structure may have changed)"

    return result


def fetch_fundamentals(tickers: list[str], **_kwargs) -> pd.DataFrame:
    """Sequential screener.in scrape with warmed-up shared session."""
    n = len(tickers)
    print(f"Scraping screener.in for {n} tickers (sequential, {FETCH_DELAY}s delay)")
    print(f"  HTTP library: {'curl_cffi (browser TLS impersonation)' if USE_CURL_CFFI else 'requests (plain)'}")

    session = _make_session()

    results: list[dict[str, Any]] = []
    t0 = time.time()

    for i, ticker in enumerate(tickers, 1):
        row = scrape_screener(session, ticker)
        results.append(row)

        if i % 25 == 0 or i == n or (i <= 5):  # more frequent early progress for debugging
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed else 0
            eta = (n - i) / rate if rate else 0
            n_ok_so_far = sum(1 for r in results if r["error"] is None)
            print(f"  {i}/{n} · ok={n_ok_so_far} · last={ticker!r} err={results[-1].get('error', 'ok')!r:.80s} · {elapsed:.0f}s · ETA {eta:.0f}s")

        if i < n:
            time.sleep(FETCH_DELAY)

    df = pd.DataFrame(results)
    n_ok = df["error"].isna().sum()
    print(f"\nFundamentals success: {n_ok}/{n} ({n_ok/n*100:.0f}%)")

    if n_ok < n * 0.7:
        errs = df[df["error"].notna()]["error"]
        print("Top error types:")
        for err, count in errs.value_counts().head(3).items():
            print(f"  ({count}x) {err[:200]}")
        if _DEBUG_SAVED[0]:
            print(f"\n  First failed response saved to {_DEBUG_PATH} — download the artifact to inspect.")

    # Field coverage — critical diagnostic
    _print_field_coverage(df)

    return df


# Fields we expect to see. Coverage below 30% = parser likely broken.
_EXPECTED_FIELDS = {
    "top ratios":   ["market_cap_cr", "pe_ratio", "roe", "roce", "current_price"],
    "shareholding": ["promoter_holding", "promoter_pledge"],
    "growth rates": ["sales_growth_5y", "profit_growth_5y"],
    "p&l ratios":   ["operating_margin", "debt_to_equity"],
}


def _print_field_coverage(df: pd.DataFrame) -> None:
    """Print how many fetched rows have each expected field populated."""
    successful = df[df["error"].isna()] if "error" in df.columns else df
    n = len(successful) or 1
    print("\nField coverage (across successfully-fetched tickers):")
    any_broken = False
    for group, fields in _EXPECTED_FIELDS.items():
        for f in fields:
            if f not in successful.columns:
                print(f"  {f:24s} MISSING (parser never wrote this column)")
                any_broken = True
                continue
            present = successful[f].notna().sum()
            pct = present / n * 100
            flag = ""
            if pct < 30:
                flag = "  <- PARSER LIKELY BROKEN"
                any_broken = True
            elif pct < 80:
                flag = "  <- partial"
            print(f"  {f:24s} {present:4d}/{n} ({pct:5.1f}%){flag}")
    if any_broken:
        print("\n  Some fields have low coverage -> filters requiring them will exclude most rows in strict mode.")
        print("  Options: run with --permissive, or fix the affected parsers in src/fetch.py.")
