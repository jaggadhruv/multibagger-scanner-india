"""
India Multibagger Screener — main entry point.

Pipeline:
  1. Universe: NSE Nifty Midcap 150 + Smallcap 250 (~400 tickers)
  2. Fetch fundamentals from screener.in (sequential, ~5 min)
  3. Apply filters (India-specific: promoter holding, pledge)
  4. Compute Multibagger Score (with India weights inc. promoter factor)
  5. Cooldown (default 60s) to let Yahoo rate limits reset
  6. Fetch technicals via yfinance with .NS suffix
  7. Merge and generate HTML report

Usage:
    python main.py                            # full run: ~10-15 min
    python main.py --sample                   # quick smoke test (~20 tickers)
    python main.py --limit 100                # first 100 for iteration
    python main.py --skip-fundamentals        # reuse cached scored.csv (retry technicals)
    python main.py --skip-technicals          # fundamentals-only report
    python main.py --wait-before-technicals 120   # longer cooldown
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from src.universe import get_universe, get_sample_tickers
from src.fetch import fetch_fundamentals
from src.screen import apply_filters
from src.score import compute_scores
from src.technicals import fetch_technicals
from src.report import generate_html_report


def _cooldown(seconds: int, label: str = "cooldown"):
    """Sleep with a visible countdown so long waits don't look like a hang."""
    if seconds <= 0:
        return
    print(f"\n{label}: waiting {seconds}s to let Yahoo rate limit clear...")
    remaining = seconds
    while remaining > 0:
        step = min(10, remaining)
        time.sleep(step)
        remaining -= step
        if remaining > 0:
            print(f"  {remaining}s remaining...")
    print("  done — resuming.")


def main():
    p = argparse.ArgumentParser(description="India multibagger stock screener")
    p.add_argument("--sample", action="store_true",
                   help="Use a hardcoded ~20-ticker sample (for quick tests)")
    p.add_argument("--limit", type=int, default=None,
                   help="Limit universe to first N tickers")
    p.add_argument("--midcap-only", action="store_true",
                   help="Use only Nifty Midcap 150 (skip Smallcap 250)")
    p.add_argument("--smallcap-only", action="store_true",
                   help="Use only Nifty Smallcap 250 (skip Midcap 150)")
    p.add_argument("--permissive", action="store_true",
                   help="Include rows with missing data in filtering (non-strict)")
    p.add_argument("--top", type=int, default=50,
                   help="Show top N in HTML report (default 50)")
    p.add_argument("--output-dir", default="output",
                   help="Directory for CSV + HTML outputs")
    p.add_argument("--wait-before-technicals", type=int, default=60,
                   help="Seconds to wait between fundamentals and technicals fetch")
    p.add_argument("--skip-fundamentals", action="store_true",
                   help="Skip fundamentals — load from cached scored.csv")
    p.add_argument("--skip-technicals", action="store_true",
                   help="Skip technicals — fundamentals-only report")
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    if args.skip_fundamentals:
        cached = output_dir / "scored.csv"
        if not cached.exists():
            print(f"ERROR: --skip-fundamentals requires {cached} to exist.")
            sys.exit(1)
        print("=" * 60)
        print("STEP 1-4: SKIPPED (loading cached scored.csv)")
        print("=" * 60)
        scored = pd.read_csv(cached)
        print(f"Loaded {len(scored)} cached candidates from {cached}")
        fetched_len = len(scored)
        universe_size = fetched_len
    else:
        # STEP 1: Universe
        print("=" * 60)
        print("STEP 1: Building ticker universe")
        print("=" * 60)
        if args.sample:
            tickers = get_sample_tickers()
            print(f"Using sample universe: {len(tickers)} tickers")
        elif args.midcap_only:
            tickers = get_universe(include_midcap=True, include_smallcap=False)
        elif args.smallcap_only:
            tickers = get_universe(include_midcap=False, include_smallcap=True)
        else:
            tickers = get_universe()
        if args.limit:
            tickers = tickers[: args.limit]
            print(f"Limited to first {len(tickers)}")
        if not tickers:
            print("ERROR: No tickers to process. Check NSE archives access.")
            sys.exit(1)
        universe_size = len(tickers)

        # STEP 2: Fetch fundamentals from screener.in
        print("\n" + "=" * 60)
        print("STEP 2: Fetching fundamentals from screener.in")
        print("=" * 60)
        raw = fetch_fundamentals(tickers)
        raw.to_csv(output_dir / "raw_data.csv", index=False)

        fetched = raw[raw["error"].isna()].copy()
        fetched_len = len(fetched)
        print(f"Rows with data: {fetched_len}/{len(raw)}")

        if fetched_len == 0:
            print("\nERROR: Zero successful fetches from screener.in.")
            print("Check output/raw_data.csv 'error' column for the cause.")
            sys.exit(1)

        # STEP 3: Filter
        print("\n" + "=" * 60)
        print("STEP 3: Applying filters")
        print("=" * 60)
        filtered = apply_filters(fetched, strict=not args.permissive)
        if len(filtered) == 0:
            print("\nNo candidates passed filters. Try --permissive or loosen thresholds in src/screen.py.")
            sys.exit(0)
        filtered.to_csv(output_dir / "filtered.csv", index=False)

        # STEP 4: Score
        print("\n" + "=" * 60)
        print("STEP 4: Fundamental scoring")
        print("=" * 60)
        scored = compute_scores(filtered)
        scored.to_csv(output_dir / "scored.csv", index=False)
        print(f"Scored data saved: {output_dir/'scored.csv'} ({len(scored)} candidates)")

    # STEP 5: Technicals (with cooldown)
    if not args.skip_technicals:
        _cooldown(args.wait_before_technicals,
                  label="Cooldown before technicals fetch")

        print("\n" + "=" * 60)
        print("STEP 5: Technical analysis (yfinance .NS, sequential)")
        print("=" * 60)
        technicals = fetch_technicals(scored["symbol"].tolist())
        technicals.to_csv(output_dir / "technicals.csv", index=False)

        scored = scored.merge(technicals, on="symbol", how="left", suffixes=("", "_tech"))
        scored.to_csv(output_dir / "final.csv", index=False)

        if "technical_score" not in scored.columns or scored["technical_score"].isna().all():
            print("\n" + "!" * 60)
            print("WARNING: technical_score column is empty or missing.")
            print("Check output/technicals.csv → 'technical_error' column.")
            print("Tip: re-run with --skip-fundamentals to retry just technicals.")
            print("!" * 60)
    else:
        print("\nSTEP 5: SKIPPED (--skip-technicals).")

    # Console preview
    print("\nTop 10:")
    preview_cols = ["symbol", "name", "market_cap_cr", "multibagger_score",
                    "technical_score", "supertrend_weekly_signal",
                    "supertrend_daily_signal", "promoter_holding", "promoter_pledge",
                    "roe", "roce", "rationale"]
    preview_cols = [c for c in preview_cols if c in scored.columns]
    with pd.option_context("display.max_columns", None, "display.width", 280,
                            "display.max_colwidth", 45):
        print(scored[preview_cols].head(10).to_string(index=False))

    # STEP 6: Report
    print("\n" + "=" * 60)
    print("STEP 6: Generating HTML report")
    print("=" * 60)
    report_path = generate_html_report(
        scored_df=scored,
        universe_size=universe_size,
        fetched_size=fetched_len,
        output_path=output_dir / "index.html",
        top_n=args.top,
    )
    print(f"\nDone. Open in browser:\n  file://{report_path.resolve()}")


if __name__ == "__main__":
    main()
