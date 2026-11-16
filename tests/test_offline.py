"""
Offline tests: no network, about 5 seconds.

    python -m tests.test_offline        (or: python -m pytest tests)

The screener.in parser is tested against a page built with the site's real
row labels and the figures shown on the live Astral page, so a pass here
means the parser reads the numbers a person would read off the site.
"""
from __future__ import annotations
import contextlib
import io
import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config as cfg  # noqa: E402
from src import fundamentals as fund  # noqa: E402
from src import tracklog  # noqa: E402
from src.checklist import classify, fundamental_items  # noqa: E402
from src.universe import exclusion_reason  # noqa: E402
from tests.fakes import ASTRAL, FakeYahoo, make_page, price_path, strong_page  # noqa: E402


def checks(rec) -> dict:
    return {i["n"]: i for i in fundamental_items(rec, cfg)[0]}


# ------------------------------------------------------------------ #
# Parser
# ------------------------------------------------------------------ #

def test_parser_reads_the_astral_page_correctly():
    page = fund.parse_page(make_page(**ASTRAL))
    assert page["name"] == "Astral Ltd"
    assert page["market_cap"] == 33689 and page["pe"] == 56.9 and page["roce_now"] == 19.2
    assert page["tables_found"] == ["annual", "balance", "cashflow", "holding_q", "holding_y", "quarters", "ratios"]
    assert page["fy_dates"] == ["Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"]
    assert page["revenue"] == [5158, 5641, 5832, 6569]                 # the TTM column (7,196) is not a fiscal year
    assert page["op_income"] == [809, 924, 946, 1062]                  # sales minus expenses
    assert page["cfo"] == [557, 823, 630, 1117]
    assert page["fcf"] == [247, 273, 90, 661]
    assert page["roce"] == [23, 22, 20, 19]
    assert abs(page["debt_to_equity"] - 120 / (27 + 4212)) < 1e-9      # latest column is the Sep 2026 half-year
    assert page["recent_q"] == "Sep 2026"
    assert abs(page["recent_q_growth"] - (1988 / 1577 - 1) * 100) < 1e-9   # Sep 2026 against Sep 2025
    assert page["promoter_holding"] == 54.22
    assert abs(page["promoter_change_pp"] - 0.01) < 1e-9               # 54.22 now, 54.21 four quarters ago
    assert page["promoter_pledge"] is None and page["is_financial"] is False
    assert page["industry"] == "Industrials / Capital Goods / Industrial Products / Plastic Products - Industrial"


def test_astral_fails_on_growth_exactly_as_the_site_says():
    # screener.in itself shows "Compounded Sales Growth, 3 Years: 8%"
    rec = fund.build_record({"ticker": "ASTRAL", "sector": "Capital Goods"}, {**fund.parse_page(make_page(**ASTRAL)), "error": None}, cfg)
    c = checks(rec)
    assert c[1]["ok"] is False and c[1]["detail"].startswith("8% a year")
    assert c[2]["ok"] is True                                          # sales did rise every year
    assert c[6]["ok"] is True and c[7]["ok"] is True                   # low debt, promoters at 54%
    assert classify(list(c.values()))["gate1"] is False


def test_strong_company_passes_gates_one_and_two():
    rec = fund.build_record({"ticker": "GOODCO", "sector": "Capital Goods"}, {**fund.parse_page(strong_page("Good Co Ltd")), "error": None}, cfg)
    c = checks(rec)
    assert all(c[n]["ok"] is True for n in range(1, 10)), {n: (i["ok"], i["detail"]) for n, i in c.items()}
    assert rec["market_cap"] == 12500


def test_pledge_and_promoter_selling_are_caught():
    html = strong_page("Pledged Ltd", cons=["Promoters have pledged 34.5% of their holding."])
    page = fund.parse_page(html)
    assert page["promoter_pledge"] == 34.5
    rec = fund.build_record({"ticker": "P"}, {**page, "error": None}, cfg)
    assert rec["extra"][1]["ok"] is False and "34.5% pledged" in rec["extra"][1]["detail"]

    selling = fund.parse_page(strong_page("Seller Ltd", promoters_q=[62.0] * 9 + [58.0] * 3))
    rec = fund.build_record({"ticker": "S"}, {**selling, "error": None}, cfg)
    assert rec["extra"][1]["ok"] is False and "down 4.0 points" in rec["extra"][1]["detail"]

    low = fund.parse_page(strong_page("Low Ltd", promoters_q=[22.0] * 12))
    assert fund.build_record({"ticker": "L"}, {**low, "error": None}, cfg)["extra"][1]["ok"] is False


def test_heavy_borrowing_fails_the_debt_check():
    page = fund.parse_page(strong_page("Levered Ltd", borrowings=[3000] * 13))
    rec = fund.build_record({"ticker": "LEV"}, {**page, "error": None}, cfg)
    assert rec["extra"][0]["ok"] is False


def test_lenders_are_recognised_from_their_own_page():
    page = fund.parse_page(strong_page("Some Bank Ltd", financial=True))
    assert page["is_financial"] is True
    assert page["revenue"][-1] is not None                             # 'Revenue' row is still read


def test_page_without_tables_gives_empty_series_not_a_crash():
    page = fund.parse_page("<html><body><h1>Blocked</h1><p>Just a moment...</p></body></html>")
    assert page["revenue"] == [] and page["tables_found"] == []
    assert fund.build_record({"ticker": "X"}, {**page, "error": "fewer than 3 years of sales on the page"}, cfg)["status"] == "no_data"


def test_standalone_page_is_used_when_consolidated_is_empty():
    full = strong_page("Solo Ltd")
    empty = re.sub(r"<td>[^<]*</td>", "<td></td>", full)        # same page with every number blank
    served = []

    def fake_fetch(session, symbol, consolidated):
        served.append(consolidated)
        return (empty if consolidated else full), ""

    with patch.object(fund, "fetch_page", fake_fetch), patch("time.sleep"):
        page = fund.scrape_company(None, "SOLO", 0)
    assert served == [True, False] and page["basis"] == "standalone" and page["error"] is None


def test_industry_exclusions():
    assert exclusion_reason("Financial Services", "", cfg)
    assert exclusion_reason("Metals & Mining", "", cfg)
    assert exclusion_reason("Capital Goods", "Metals & Mining / Steel / Iron & Steel Products", cfg)
    assert exclusion_reason("Capital Goods", "Industrials / Capital Goods / Electrical Equipment", cfg) is None
    assert exclusion_reason("Healthcare", "", cfg) is None


# ------------------------------------------------------------------ #
# Universe sources
# ------------------------------------------------------------------ #

def test_saved_index_lists_are_used_when_nse_refuses():
    from src import universe
    with patch.object(universe, "_download", lambda url: None), patch.object(universe, "SNAPSHOT", ROOT / "data" / "universe_snapshot.csv"), \
            patch.object(universe, "CUSTOM_UNIVERSE", Path("no-such-file.csv")), contextlib.redirect_stdout(io.StringIO()):
        rows, described = universe.get_universe()
    assert len(rows) == 400 and "saved list of" in described
    tickers = {r["ticker"] for r in rows}
    assert {"ASTRAL", "PERSISTENT", "KPITTECH", "M&MFIN"} <= tickers and not any(t.startswith("DUMMY") for t in tickers)
    in_scope = [r for r in rows if not exclusion_reason(r["sector"], "", cfg)]
    assert 250 < len(in_scope) < 320                                    # lenders, metals, oil and gas, realty removed
    assert all(r["sector"] != "Financial Services" for r in in_scope)


def test_live_index_download_refreshes_the_saved_copy():
    from src import universe

    def fake_download(url):
        if "nsearchives" in url:
            return "<html>Access Denied</html>"                         # first address blocked, second one works
        n = 150 if "midcap150" in url else 250
        tag = "M" if n == 150 else "S"
        lines = [f"Company {tag}{i} Ltd.,Capital Goods,{tag}SYM{i},EQ,INE{i:06d}" for i in range(n)]
        return "Company Name,Industry,Symbol,Series,ISIN Code\n" + "\n".join(lines) + "\nDummy X Ltd.,Capital Goods,DUMMYX,EQ,DUM1\n"

    with tempfile.TemporaryDirectory() as tmp, patch.object(universe, "_download", fake_download), \
            patch.object(universe, "SNAPSHOT", Path(tmp) / "snap.csv"), \
            patch.object(universe, "CUSTOM_UNIVERSE", Path("no-such-file.csv")), contextlib.redirect_stdout(io.StringIO()):
        rows, described = universe.get_universe()
        assert len(rows) == 400 and described == "Nifty Midcap 150 + Smallcap 250"
        saved = pd.read_csv(Path(tmp) / "snap.csv")
        assert list(saved.columns) == ["Index", "Company Name", "Industry", "Symbol", "As Of"] and len(saved) == 402


# ------------------------------------------------------------------ #
# One full run, universe to report
# ------------------------------------------------------------------ #

PAGES = {
    "ALFA": strong_page("Alfa Electricals Ltd"),                                   # A, established
    "BRAV": strong_page("Bravo Controls Ltd"),                                     # A, emerging
    "CHAR": strong_page("Charlie Pumps Ltd"),                                      # B, chart not ready
    "DELT": strong_page("Delta Cables Ltd", expenses=[round(300 * 1.25 ** i * 0.82) for i in range(12)]),  # C, flat margin
    "ASTRAL": make_page(**ASTRAL),                                                 # 8% growth, dropped
    "FOXT": strong_page("Foxtrot Giant Ltd", market_cap="95,000"),                 # passes, but too large
    "LENDR": strong_page("Lender Ltd", financial=True),                            # found to be a lender on its page
}


def run_main(world, universe) -> str:
    import main

    def fake_fetch(session, symbol, consolidated):
        return (PAGES[symbol], "") if symbol in PAGES else (None, "404 not found")

    out = io.StringIO()
    with patch("yfinance.Ticker", world.Ticker), patch("time.sleep"), patch.object(sys, "argv", ["main.py"]), \
            patch.object(fund, "fetch_page", fake_fetch), patch.object(fund, "make_session", lambda: None), \
            patch.object(main, "get_universe", lambda: (universe, "Nifty Midcap 150 + Smallcap 250 (test)")), \
            contextlib.redirect_stdout(out):
        main.main()
    return out.getvalue()


def test_full_run_end_to_end():
    world = FakeYahoo({
        "ALFA.NS": price_path("established", 11), "BRAV.NS": price_path("emerging", 12),
        "CHAR.NS": price_path("downtrend", 13), "DELT.NS": price_path("established", 14),
        "FOXT.NS": price_path("established", 15), "^NSEI": price_path("index", 99),
    })
    universe = [{"ticker": t, "name": "", "sector": "Capital Goods", "industry": ""}
                for t in ["ALFA", "BRAV", "CHAR", "DELT", "ASTRAL", "FOXT", "LENDR", "GONE"]]
    universe.append({"ticker": "BIGBANK", "name": "Big Bank", "sector": "Financial Services", "industry": ""})
    here = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            log_text = run_main(world, universe)
            rows = pd.read_csv("output/all_companies.csv").set_index("ticker")
            assert rows.loc["ALFA", "tier"] == "A" and rows.loc["ALFA", "stage"].startswith("Established")
            assert rows.loc["BRAV", "tier"] == "A" and rows.loc["BRAV", "stage"].startswith("Emerging")
            assert rows.loc["CHAR", "tier"] == "B"
            assert rows.loc["DELT", "tier"] == "C"
            assert rows.loc["ASTRAL", "tier"] == "-"
            assert rows.loc["FOXT", "tier"] == "-" and "size band" in rows.loc["FOXT", "dropped"]
            for gone in ("LENDR", "BIGBANK", "GONE"):
                assert gone not in rows.index
            assert rows.loc["ALFA", "score"] == 12 and rows.loc["ALFA", "name"] == "Alfa Electricals Ltd"
            # Yahoo was asked only for the index and the gate-1 passers
            assert set(world.calls) == {"^NSEI", "ALFA.NS", "BRAV.NS", "CHAR.NS", "DELT.NS", "FOXT.NS"}, world.calls

            html = Path("output/index.html").read_text(encoding="utf-8")
            for needle in ("ALFA", "BRAV", "CHAR", "DELT", "₹12,500 Cr", "screener.in/company/ALFA/", "Promoters aligned"):
                assert needle in html, needle
            assert "FOXT" not in html and "LENDR" not in html
            assert "What the pages yielded" in log_text and "LOW" not in log_text
            assert sorted(r["ticker"] for r in tracklog.load("data/picks_log.csv")) == ["ALFA", "BRAV"]
            assert Path("output/raw_pages.csv").exists()
        finally:
            os.chdir(here)


def test_blocked_site_is_reported_loudly():
    import main
    here = os.getcwd()
    universe = [{"ticker": f"S{i:02d}", "name": "", "sector": "Capital Goods", "industry": ""} for i in range(25)]
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            with patch("yfinance.Ticker", FakeYahoo().Ticker), patch("time.sleep"), patch.object(sys, "argv", ["main.py"]), \
                    patch.object(fund, "fetch_page", lambda *a: (None, "HTTP 403")), patch.object(fund, "make_session", lambda: None), \
                    patch.object(main, "get_universe", lambda: (universe, "Nifty Midcap 150 + Smallcap 250 (test)")), \
                    contextlib.redirect_stdout(out):
                main.main()
            html = Path("output/index.html").read_text(encoding="utf-8")
            assert "No screener.in page could be read" in html
            assert "none of the first 10 pages could be read" in out.getvalue()
        finally:
            os.chdir(here)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"ok   {name}")
    print(f"\nAll {len(tests)} tests passed.")
