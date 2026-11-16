"""
India Multibagger Shortlist: main entry point.

    python main.py              full run (about 400 screener.in pages, 10-12 minutes)
    python main.py --sample     12 tickers, quick check that everything works
    python main.py --limit 60   first 60 in-scope tickers

Steps
    1. Universe (Nifty Midcap 150 + Smallcap 250, or input/universe.csv) and industry exclusions
    2. One screener.in page per company: 4 years of results, balance sheet, cash flow,
       ROCE, latest quarter, promoter holding
    3. Business checklist: gate 1 (proven) and gate 2 (inflecting)
    4. Prices from Yahoo (.NS) for the gate-1 passers only, then gate 3 (chart)
    5. Tiers, track record, output/index.html and CSV files
"""
from __future__ import annotations
import argparse
import csv
import sys
from pathlib import Path

import config as cfg
from src import fundamentals as fund
from src.pipeline import finish_run
from src.universe import SAMPLE, exclusion_reason, get_universe


def write_raw(pages: dict, path: Path) -> None:
    """What was read from each page, for checking the parser against the site."""
    cols = ["ticker", "error", "basis", "name", "industry", "is_financial", "tables_found", "fy_dates", "revenue",
            "op_income", "net_income", "cfo", "fcf", "roce", "debt_to_equity", "promoter_holding",
            "promoter_change_pp", "promoter_pledge", "recent_q", "recent_q_growth", "market_cap", "pe"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for t, p in pages.items():
            w.writerow([t] + [" | ".join("" if x is None else str(x) for x in v) if isinstance(v, list) else v
                              for v in (p.get(c) for c in cols[1:])])


def main() -> None:
    p = argparse.ArgumentParser(description="India multibagger shortlist")
    p.add_argument("--sample", action="store_true", help="12 tickers, for a quick check")
    p.add_argument("--limit", type=int, default=None, help="only the first N in-scope tickers")
    args = p.parse_args()
    health = {"warnings": [], "notes": []}

    print("=" * 64 + "\nUniverse\n" + "=" * 64)
    if args.sample:
        universe, described = list(SAMPLE), "sample of 12 tickers"
    else:
        universe, described = get_universe()
    if not universe:
        print("ERROR: no tickers. The NSE index files could not be read; try again or add input/universe.csv")
        sys.exit(1)
    cfg.UNIVERSE_NAME = described
    if not args.sample and described.startswith("Nifty") and len(universe) < 350:
        health["warnings"].append(f"Only {len(universe)} tickers were read from NSE (about 400 expected). "
                                  "One of the two index files probably failed to load.")

    in_scope = [m for m in universe if not exclusion_reason(m.get("sector"), "", cfg)]
    excluded = len(universe) - len(in_scope)
    if args.limit:
        in_scope = in_scope[: args.limit]
    print(f"{len(universe)} tickers, {excluded} outside scope by NSE industry group, {len(in_scope)} to screen")

    print("\n" + "=" * 64 + "\nscreener.in pages\n" + "=" * 64)
    pages = fund.scrape_all([m["ticker"] for m in in_scope], cfg)
    write_raw(pages, Path("output/raw_pages.csv"))

    cov = fund.coverage(pages)
    print(f"\nWhat the pages yielded ({cov['usable']} usable of {len(in_scope)}):")
    for name, count in cov.items():
        if name != "usable":
            flag = "   <-- LOW: the parser may not match the site any more" if cov["usable"] and count < 0.5 * cov["usable"] else ""
            print(f"  {name:24s} {count:4d}{flag}")
    if cov["usable"] == 0:
        health["warnings"].append("No screener.in page could be read. If output/debug_response.html exists it shows "
                                  "what the site returned; the usual cause is the site refusing this machine.")

    # Second round of exclusions, from what the pages themselves say
    records, late = [], 0
    for meta in in_scope:
        page = pages.get(meta["ticker"])
        rec = fund.build_record(meta, page, cfg)
        if rec["status"] == "ok":
            if rec.get("is_financial") or exclusion_reason(rec.get("sector"), rec.get("industry"), cfg):
                late += 1
                continue
        records.append(rec)
    if late:
        print(f"{late} more excluded after reading their pages (lenders or commodity industries)")

    counts = {"universe": len(universe), "in_scope": len(in_scope) - late}
    finish_run(cfg, records, counts, health)
    print("\nDone. Open output/index.html")


if __name__ == "__main__":
    main()
