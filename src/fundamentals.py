"""
Multi-year fundamentals for Indian stocks, read from screener.in company pages.

One page per company carries everything the checklist needs: about 12 years
of profit and loss, balance sheet, cash flow and ROCE, 13 quarters of results
and the shareholding pattern.

How the page is read
    Tables are recognised by the ROW LABELS they contain ("Sales", "Net
    Profit", "Borrowings", "Cash from Operating Activity", "ROCE %",
    "Promoters"), never by their position or CSS class. Quarterly and annual
    tables are told apart by the gap between their column dates. That keeps
    the parser working when screener.in restyles the page.

Two things screener.in does NOT show on the public page, and how they are
handled
    Debt to equity   computed here: Borrowings / (Equity Capital + Reserves)
    Promoter pledge  only mentioned in the page's "Cons" list when it is
                     material ("Promoters have pledged 34.5% of their
                     holding"). No mention is treated as no pledge flagged.
"""
from __future__ import annotations
import re
import time
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src.checklist import num

# curl_cffi (installed with yfinance) presents a real browser's TLS fingerprint.
# Plain `requests` tends to be refused by screener.in from cloud servers.
try:
    from curl_cffi import requests as http
    USE_CURL_CFFI = True
    IMPERSONATE = "chrome120"
except ImportError:  # pragma: no cover
    import requests as http
    USE_CURL_CFFI = False
    IMPERSONATE = None

BASE_URL = "https://www.screener.in/company"
HOMEPAGE_URL = "https://www.screener.in/"
DEBUG_PATH = Path("output/debug_response.html")
# Same session settings as the previous version of this tool, which screener.in accepted.
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/121.0.0.0 Safari/537.36"),
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
_debug_saved = [False]
_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


# ------------------------------------------------------------------ #
# Text helpers
# ------------------------------------------------------------------ #

def to_float(text):
    """'₹ 1,234.5 Cr.' / '17%' / '-343' -> float. Blank or dash -> None."""
    if text is None:
        return None
    s = str(text).replace("\xa0", " ").strip()
    if not s or s in ("-", "—", "–"):
        return None
    m = _NUM_RE.search(s.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def norm_label(text: str) -> str:
    """'Sales\\xa0+' -> 'sales', 'Cash from Operating Activity +' -> 'cash from operating activity'."""
    t = (text or "").replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*\+$", "", t)
    return t.lower()


def parse_period(text: str):
    """'Mar 2025' -> Timestamp(2025-03-01); 'TTM' -> 'TTM'; anything else -> None."""
    t = (text or "").replace("\xa0", " ").strip()
    if t.upper() == "TTM":
        return "TTM"
    try:
        return pd.Timestamp(pd.to_datetime(t, format="%b %Y"))
    except (ValueError, TypeError):
        return None


# ------------------------------------------------------------------ #
# Generic table reading
# ------------------------------------------------------------------ #

def read_tables(soup: BeautifulSoup) -> list[dict]:
    """Every table on the page as {'periods': [...], 'rows': {label: [cell text, ...]}}."""
    tables = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if len(trs) < 2:
            continue
        head = [c.get_text(" ", strip=True) for c in trs[0].find_all(["th", "td"])]
        rows = {}
        for tr in trs[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = norm_label(cells[0].get_text(" ", strip=True))
            if label and label not in rows:
                rows[label] = [c.get_text(" ", strip=True) for c in cells[1:]]
        if rows:
            tables.append({"periods": [parse_period(h) for h in head[1:]], "rows": rows})
    return tables


def _row(tbl: dict, *prefixes: str):
    """Values of the first row whose label starts with one of the prefixes."""
    for label, cells in tbl["rows"].items():
        if label.startswith(prefixes):
            return [to_float(c) for c in cells]
    return None


def _has(tbl: dict, *prefixes: str) -> bool:
    return any(label.startswith(prefixes) for label in tbl["rows"])


def _is_quarterly(tbl: dict) -> bool:
    dates = [p for p in tbl["periods"] if isinstance(p, pd.Timestamp)]
    if len(dates) < 3:
        return False
    gaps = sorted((b.year - a.year) * 12 + (b.month - a.month) for a, b in zip(dates, dates[1:]))
    return gaps[len(gaps) // 2] <= 4


def classify_tables(tables: list[dict]) -> dict:
    """Pick out the tables we need by what they contain."""
    found: dict[str, dict] = {}
    for t in tables:
        if _has(t, "sales", "revenue") and _has(t, "net profit"):
            kind = "quarters" if _is_quarterly(t) else "annual"
        elif _has(t, "borrowing") or _has(t, "reserves"):
            kind = "balance"
        elif _has(t, "cash from operating"):
            kind = "cashflow"
        elif _has(t, "roce %"):
            kind = "ratios"
        elif _has(t, "promoters"):
            kind = "holding_q" if _is_quarterly(t) else "holding_y"
        else:
            continue
        found.setdefault(kind, t)
    return found


def _by_period(tbl: dict | None, *prefixes: str) -> dict:
    """{period: value} for one row of a table."""
    if not tbl:
        return {}
    values = _row(tbl, *prefixes)
    if values is None:
        return {}
    return {p: v for p, v in zip(tbl["periods"], values) if p is not None}


# ------------------------------------------------------------------ #
# One company page -> plain dict
# ------------------------------------------------------------------ #

def _top_ratios(soup: BeautifulSoup) -> dict:
    out = {}
    for li in soup.find_all("li"):
        name_el = li.find(class_="name")
        if name_el is None:
            continue
        name = norm_label(name_el.get_text(" ", strip=True))
        full = li.get_text(" ", strip=True)
        value = full[len(name_el.get_text(" ", strip=True)):]
        if name.startswith("market cap"):
            out["market_cap"] = to_float(value)
        elif name.startswith("current price"):
            out["price"] = to_float(value)
        elif name.startswith("stock p/e"):
            out["pe"] = to_float(value)
        elif name == "roce":
            out["roce_now"] = to_float(value)
        elif name == "roe":
            out["roe_now"] = to_float(value)
    return out


def _sector_line(soup: BeautifulSoup) -> str:
    """The 'Industrials > Capital Goods > ...' breadcrumb in the peers section."""
    peers = soup.find(id="peers")
    if peers is None:
        return ""
    links = [a.get_text(" ", strip=True) for a in peers.find_all("a") if "/market/" in (a.get("href") or "")]
    if links:
        return " / ".join(dict.fromkeys(links))
    sub = peers.find("p")
    return re.sub(r"\s+", " ", sub.get_text(" ", strip=True)) if sub else ""


def parse_page(html: str) -> dict:
    """Everything we use from one screener.in company page."""
    soup = BeautifulSoup(html, "lxml")
    found = classify_tables(read_tables(soup))
    out = {"name": "", "industry": _sector_line(soup), "tables_found": sorted(found)}
    h1 = soup.find("h1")
    if h1:
        out["name"] = h1.get_text(" ", strip=True)
    out.update(_top_ratios(soup))

    annual = found.get("annual")
    out["is_financial"] = bool(annual and _has(annual, "financing profit", "financing margin"))
    fy = [p for p in (annual["periods"] if annual else []) if isinstance(p, pd.Timestamp)][-4:]
    out["fy_dates"] = [d.strftime("%b %Y") for d in fy]

    def series(tbl, *prefixes):
        by = _by_period(tbl, *prefixes)
        return [by.get(d) for d in fy]

    out["revenue"] = series(annual, "sales", "revenue")
    out["op_income"] = series(annual, "operating profit", "financing profit")
    out["net_income"] = series(annual, "net profit")
    out["cfo"] = series(found.get("cashflow"), "cash from operating")
    out["fcf"] = series(found.get("cashflow"), "free cash flow")
    out["roce"] = series(found.get("ratios"), "roce %")

    # Balance sheet: latest column (often a half-year snapshot newer than the last full year)
    out["debt_to_equity"] = None
    bal = found.get("balance")
    if bal:
        idx = [i for i, p in enumerate(bal["periods"]) if isinstance(p, pd.Timestamp)]
        cap, res, debt = _row(bal, "equity capital"), _row(bal, "reserves"), _row(bal, "borrowing")
        for i in reversed(idx):
            c = cap[i] if cap and i < len(cap) else None
            r = res[i] if res and i < len(res) else None
            d = debt[i] if debt and i < len(debt) else None
            if c is not None and r is not None and d is not None:
                funds = c + r
                out["debt_to_equity"] = (d / funds) if funds > 0 else float("inf")
                out["borrowings"] = d
                break

    # Latest quarter against the same quarter a year earlier
    out["recent_q_growth"], out["recent_q"] = None, None
    q_sales = _by_period(found.get("quarters"), "sales", "revenue")
    q_dates = sorted(p for p, v in q_sales.items() if isinstance(p, pd.Timestamp) and v is not None)
    if q_dates:
        latest = q_dates[-1]
        year_ago = latest - pd.DateOffset(years=1)
        prev = q_sales.get(pd.Timestamp(year_ago))
        if prev and prev > 0:
            out["recent_q_growth"] = (q_sales[latest] / prev - 1.0) * 100.0
            out["recent_q"] = latest.strftime("%b %Y")

    # Promoter holding now and about a year ago
    out["promoter_holding"], out["promoter_change_pp"] = None, None
    hold = found.get("holding_q") or found.get("holding_y")
    if hold:
        values = [v for v in (_row(hold, "promoters") or []) if v is not None]
        if values:
            out["promoter_holding"] = values[-1]
            back = 4 if hold is found.get("holding_q") else 1
            if len(values) > back:
                out["promoter_change_pp"] = values[-1] - values[-1 - back]

    notes = soup.find(id="analysis") or soup          # the Pros / Cons block when present
    m = re.search(r"pledged\s+(\d+(?:\.\d+)?)\s*%", notes.get_text(" ", strip=True), re.I)
    out["promoter_pledge"] = float(m.group(1)) if m else None
    return out


# ------------------------------------------------------------------ #
# Fetching
# ------------------------------------------------------------------ #

def make_session():
    s = http.Session(impersonate=IMPERSONATE) if USE_CURL_CFFI else http.Session()
    s.headers.update(BROWSER_HEADERS)
    try:
        r = s.get(HOMEPAGE_URL, timeout=20)
        kind = "browser-impersonating session" if USE_CURL_CFFI else "plain session (curl_cffi missing)"
        print(f"  screener.in {kind}, homepage HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        print(f"  screener.in warm-up failed ({e}); carrying on")
    return s


def _save_debug(html: str, symbol: str, reason: str) -> None:
    if _debug_saved[0]:
        return
    try:
        DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_PATH.write_text(f"<!-- {symbol}: {reason} -->\n{html[:30000]}", encoding="utf-8")
        _debug_saved[0] = True
        print(f"  saved the first rejected response to {DEBUG_PATH}")
    except OSError:
        pass


def fetch_page(session, symbol: str, consolidated: bool) -> tuple[str | None, str]:
    url = f"{BASE_URL}/{symbol}/" + ("consolidated/" if consolidated else "")
    for attempt in (1, 2):
        try:
            r = session.get(url, timeout=25, impersonate=IMPERSONATE) if USE_CURL_CFFI else session.get(url, timeout=25)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:80]}"
            time.sleep(2)
            continue
        if r.status_code == 200:
            if "<table" not in r.text:
                _save_debug(r.text, symbol, "HTTP 200 but no tables (blocked or challenge page)")
                return None, "page has no tables (blocked?)"
            return r.text, ""
        if r.status_code == 404:
            return None, "404 not found"
        err = f"HTTP {r.status_code}"
        if r.status_code == 429 and attempt == 1:
            time.sleep(15)
            continue
        _save_debug(r.text, symbol, err)
        break
    return None, err


def _years_of_sales(page: dict) -> int:
    return sum(1 for v in page.get("revenue", []) if v is not None)


def scrape_company(session, symbol: str, delay: float) -> dict:
    """Consolidated numbers when the company reports them, otherwise standalone."""
    best, last_err = None, "unknown"
    for consolidated in (True, False):
        html, err = fetch_page(session, symbol, consolidated)
        time.sleep(delay)
        if html is None:
            last_err = err
            continue
        try:
            page = parse_page(html)
        except Exception as e:  # noqa: BLE001
            last_err = f"parse: {type(e).__name__}: {str(e)[:80]}"
            continue
        page["basis"] = "consolidated" if consolidated else "standalone"
        if best is None or _years_of_sales(page) > _years_of_sales(best):
            best = page
        if _years_of_sales(page) >= 4:
            break
    if best is None:
        return {"error": last_err}
    best["error"] = None if _years_of_sales(best) >= 3 else "fewer than 3 years of sales on the page"
    return best


def scrape_all(tickers: list[str], cfg) -> dict:
    """Sequential scrape. Gives up early if screener.in refuses the first several pages."""
    n = len(tickers)
    print(f"Reading {n} screener.in pages, one at a time (about {n * (cfg.SCREENER_DELAY + 1.0) / 60:.0f} min)")
    session = make_session()
    pages, ok, started = {}, 0, time.time()
    for i, t in enumerate(tickers, 1):
        pages[t] = scrape_company(session, t, cfg.SCREENER_DELAY)
        ok += pages[t].get("error") is None
        if i == 10 and ok == 0:
            print("  none of the first 10 pages could be read; stopping (screener.in is refusing this machine)")
            break
        if i % 25 == 0 or i == n:
            print(f"  {i}/{n} pages, {ok} usable, {(time.time() - started) / 60:.1f} min")
    return pages


# ------------------------------------------------------------------ #
# Parsed page -> record for the checklist
# ------------------------------------------------------------------ #

def build_record(meta: dict, page: dict | None, cfg) -> dict:
    rec = {**meta, "status": "no_data", "extra": []}
    if not page or page.get("error"):
        return rec
    rec.update({
        "status": "ok",
        "name": page.get("name") or meta.get("name", ""),
        "industry": page.get("industry") or meta.get("industry", ""),
        "fy_end": page["fy_dates"][-1] if page.get("fy_dates") else None,
        "revenue": page["revenue"], "op_income": page["op_income"], "net_income": page["net_income"],
        "cash_flow": page["cfo"], "roc": page["roce"],
        "recent_q_growth": page.get("recent_q_growth"),
        "market_cap": page.get("market_cap"), "pe": page.get("pe"),
        "is_financial": page.get("is_financial", False),
    })

    # Item 6: borrowings against shareholders' funds
    de, label = page.get("debt_to_equity"), "Low debt"
    if de is None:
        rec["extra"].append({"label": label, "ok": None, "detail": "no balance sheet data"})
    elif de < 0.02:
        rec["extra"].append({"label": label, "ok": True, "detail": "almost no borrowings"})
    else:
        rec["extra"].append({"label": label, "ok": de <= cfg.DEBT_TO_EQUITY_MAX,
                             "detail": f"borrowings are {de:.2f}x shareholders' funds"})

    # Item 7: promoter alignment
    holding, change, pledge = num(page.get("promoter_holding")), num(page.get("promoter_change_pp")), num(page.get("promoter_pledge"))
    label = "Promoters aligned"
    if holding is None and cfg.PROMOTER_HOLDING_MIN > 0:
        rec["extra"].append({"label": label, "ok": None, "detail": "no promoter holding on the page"})
    else:
        holding = holding or 0.0
        ok = holding >= cfg.PROMOTER_HOLDING_MIN
        detail = f"promoters hold {holding:.1f}%"
        if change is not None:
            if change <= -0.05:
                detail += f", down {abs(change):.1f} points over a year"
            elif change >= 0.05:
                detail += f", up {change:.1f} points over a year"
            ok = ok and change >= -cfg.PROMOTER_DROP_MAX_PP
        if pledge is not None:
            detail += f", {pledge:.1f}% pledged"
            ok = ok and pledge <= cfg.PROMOTER_PLEDGE_MAX
        else:
            detail += ", no pledge flagged"
        rec["extra"].append({"label": label, "ok": ok, "detail": detail})
    return rec


def coverage(pages: dict) -> dict:
    """How many pages yielded each field. Printed every run so a broken parser is obvious."""
    usable = [p for p in pages.values() if p.get("error") is None]
    fields = {
        "4 years of sales": lambda p: _years_of_sales(p) >= 4,
        "operating profit": lambda p: sum(v is not None for v in p.get("op_income", [])) >= 4,
        "net profit": lambda p: sum(v is not None for v in p.get("net_income", [])) >= 3,
        "operating cash flow": lambda p: sum(v is not None for v in p.get("cfo", [])) >= 3,
        "ROCE": lambda p: sum(v is not None for v in p.get("roce", [])) >= 3,
        "debt to equity": lambda p: p.get("debt_to_equity") is not None,
        "promoter holding": lambda p: p.get("promoter_holding") is not None,
        "latest quarter growth": lambda p: p.get("recent_q_growth") is not None,
        "market cap": lambda p: p.get("market_cap") is not None,
    }
    return {"usable": len(usable), **{name: sum(1 for p in usable if test(p)) for name, test in fields.items()}}
