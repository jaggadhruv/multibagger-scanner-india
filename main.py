"""
India Multibagger Screener — main entry point.

Pipeline:
  1. Universe: NSE Nifty Midcap 150 + Smallcap 250 (~400 tickers)
  2. Fetch fundamentals from screener.in (sequential, ~5 min)
  3. Apply filters (India-specific: promoter holding, pledge)
  4. Compute Multibagger Score (with India weights inc. promoter factor)
  5. Cooldown (default 60s)
  6. Fetch technicals via yfinance with .NS suffix
  7. ALWAYS generates HTML report — even if fetches fail — so GitHub Pages
     always has something to publish and you can see diagnostics in the browser.

Usage:
    python main.py                            # full run: ~10-15 min
    python main.py --sample                   # quick smoke test (~20 tickers)
    python main.py --limit 100                # first 100 for iteration
    python main.py --skip-fundamentals        # reuse cached scored.csv
    python main.py --skip-technicals          # fundamentals-only report
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


def _empty_scored(diagnostics: dict) -> pd.DataFrame:
    """Return an empty DataFrame that still carries diagnostic metadata for the report."""
    df = pd.DataFrame()
    df.attrs["diagnostics"] = diagnostics
    return df


def main():
    p = argparse.ArgumentParser(description="India multibagger stock screener")
    p.add_argument("--sample", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--midcap-only", action="store_true")
    p.add_argument("--smallcap-only", action="store_true")
    p.add_argument("--permissive", action="store_true")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--output-dir", default="output")
    p.add_argument("--wait-before-technicals", type=int, default=60)
    p.add_argument("--skip-fundamentals", action="store_true")
    p.add_argument("--skip-technicals", action="store_true")
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    # Diagnostic state that will be shown in the HTML if things go wrong
    diagnostics = {
        "universe_size": 0,
        "fetched_size": 0,
        "filtered_size": 0,
        "notes": [],
    }

    scored = pd.DataFrame()

    if args.skip_fundamentals:
        cached = output_dir / "scored.csv"
        if not cached.exists():
            print(f"WARNING: --skip-fundamentals requires {cached} to exist. "
                  f"Will generate empty report.")
            diagnostics["notes"].append(f"--skip-fundamentals used but {cached} missing")
        else:
            print("=" * 60)
            print("STEP 1-4: SKIPPED (loading cached scored.csv)")
            print("=" * 60)
            scored = pd.read_csv(cached)
            print(f"Loaded {len(scored)} cached candidates from {cached}")
            diagnostics["fetched_size"] = len(scored)
            diagnostics["universe_size"] = len(scored)
            diagnostics["filtered_size"] = len(scored)
    else:
        # STEP 1: Universe
        print("=" * 60)
        print("STEP 1: Building ticker universe")
        print("=" * 60)
        try:
            if args.sample:
                tickers = get_sample_tickers()
                print(f"Using sample universe: {len(tickers)} tickers")
            elif args.midcap_only:
                tickers = get_universe(include_midcap=True, include_smallcap=False)
            elif args.smallcap_only:
                tickers = get_universe(include_midcap=False, include_smallcap=True)
            else:
                tickers = get_universe()
        except Exception as e:
            print(f"ERROR fetching universe: {e}")
            tickers = []
            diagnostics["notes"].append(f"Universe fetch failed: {type(e).__name__}: {e}")

        if args.limit:
            tickers = tickers[: args.limit]
            print(f"Limited to first {len(tickers)}")

        diagnostics["universe_size"] = len(tickers)

        if not tickers:
            diagnostics["notes"].append("Universe is empty — check NSE archives access")
            print("WARNING: No tickers to process. Will generate empty report.")
        else:
            # STEP 2: Fetch fundamentals
            print("\n" + "=" * 60)
            print("STEP 2: Fetching fundamentals from screener.in")
            print("=" * 60)
            try:
                raw = fetch_fundamentals(tickers)
                raw.to_csv(output_dir / "raw_data.csv", index=False)
            except Exception as e:
                print(f"ERROR during fundamentals fetch: {type(e).__name__}: {e}")
                diagnostics["notes"].append(f"Fetch crashed: {type(e).__name__}: {e}")
                raw = pd.DataFrame({"symbol": tickers, "error": [f"crash: {e}"] * len(tickers)})
                raw.to_csv(output_dir / "raw_data.csv", index=False)

            fetched = raw[raw["error"].isna()].copy() if "error" in raw.columns else raw
            diagnostics["fetched_size"] = len(fetched)
            print(f"Rows with data: {len(fetched)}/{len(raw)}")

            if len(fetched) == 0:
                # Collect top error reasons for the diagnostic report
                if "error" in raw.columns:
                    errs = raw["error"].value_counts().head(3)
                    for err, count in errs.items():
                        diagnostics["notes"].append(f"({count}x) {str(err)[:200]}")
                diagnostics["notes"].append(
                    "Zero successful fetches from screener.in — likely IP block. "
                    "Inspect output/debug_response.html (if present) for the blocked response."
                )
                print("WARNING: Zero successful fetches. Report will be empty (diagnostic only).")
            else:
                # STEP 3: Filter
                print("\n" + "=" * 60)
                print("STEP 3: Applying filters")
                print("=" * 60)
                try:
                    filtered = apply_filters(fetched, strict=not args.permissive)
                    filtered.to_csv(output_dir / "filtered.csv", index=False)
                    diagnostics["filtered_size"] = len(filtered)
                except Exception as e:
                    print(f"ERROR during filtering: {e}")
                    diagnostics["notes"].append(f"Filter crashed: {e}")
                    filtered = pd.DataFrame()

                if len(filtered) == 0:
                    diagnostics["notes"].append(
                        "Zero candidates passed filters. "
                        "Try --permissive, or loosen thresholds in src/screen.py."
                    )
                    print("WARNING: No candidates passed filters. Report will be empty.")
                else:
                    # STEP 4: Score
                    print("\n" + "=" * 60)
                    print("STEP 4: Fundamental scoring")
                    print("=" * 60)
                    try:
                        scored = compute_scores(filtered)
                        scored.to_csv(output_dir / "scored.csv", index=False)
                        print(f"Scored {len(scored)} candidates → {output_dir/'scored.csv'}")
                    except Exception as e:
                        print(f"ERROR during scoring: {e}")
                        diagnostics["notes"].append(f"Scoring crashed: {e}")

    # STEP 5: Technicals (only if we have candidates)
    if not args.skip_technicals and len(scored) > 0 and "symbol" in scored.columns:
        _cooldown(args.wait_before_technicals, label="Cooldown before technicals fetch")

        print("\n" + "=" * 60)
        print("STEP 5: Technical analysis (yfinance .NS, sequential)")
        print("=" * 60)
        try:
            technicals = fetch_technicals(scored["symbol"].tolist())
            technicals.to_csv(output_dir / "technicals.csv", index=False)
            scored = scored.merge(technicals, on="symbol", how="left", suffixes=("", "_tech"))
            scored.to_csv(output_dir / "final.csv", index=False)

            if "technical_score" not in scored.columns or scored["technical_score"].isna().all():
                msg = "technical_score is empty — check technicals.csv for the cause"
                print(f"WARNING: {msg}")
                diagnostics["notes"].append(msg)
        except Exception as e:
            print(f"ERROR during technicals: {type(e).__name__}: {e}")
            diagnostics["notes"].append(f"Technicals crashed: {type(e).__name__}: {e}")
    elif len(scored) == 0:
        print("\nSTEP 5: SKIPPED (no candidates to fetch technicals for).")
    else:
        print("\nSTEP 5: SKIPPED (--skip-technicals).")

    # Console preview
    if len(scored) > 0:
        print("\nTop 10:")
        preview_cols = ["symbol", "name", "market_cap_cr", "multibagger_score",
                        "technical_score", "supertrend_weekly_signal",
                        "supertrend_daily_signal", "promoter_holding", "promoter_pledge",
                        "roe", "roce", "rationale"]
        preview_cols = [c for c in preview_cols if c in scored.columns]
        with pd.option_context("display.max_columns", None, "display.width", 280,
                                "display.max_colwidth", 45):
            print(scored[preview_cols].head(10).to_string(index=False))

    # STEP 6: Report — ALWAYS runs, even with 0 rows
    print("\n" + "=" * 60)
    print("STEP 6: Generating HTML report")
    print("=" * 60)
    scored.attrs["diagnostics"] = diagnostics
    report_path = generate_html_report(
        scored_df=scored,
        universe_size=diagnostics["universe_size"],
        fetched_size=diagnostics["fetched_size"],
        output_path=output_dir / "index.html",
        top_n=args.top,
        diagnostics=diagnostics,
    )
    print(f"\nDone. Report at: file://{report_path.resolve()}")
    # Exit 0 always — report exists, Pages deploy should proceed.
    sys.exit(0)


if __name__ == "__main__":
    main()
