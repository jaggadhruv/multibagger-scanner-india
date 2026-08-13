"""
Diagnostic: analyze output/raw_data.csv to see which fields the screener.in
parsers extracted successfully, and which are mostly missing.

Usage:
    python diagnose.py                    # analyzes output/raw_data.csv
    python diagnose.py path/to/other.csv  # analyzes a specific file

The output tells you which parsers are working and which need fixing.
"""
import sys
from pathlib import Path
import pandas as pd

path = sys.argv[1] if len(sys.argv) > 1 else "output/raw_data.csv"
p = Path(path)
if not p.exists():
    print(f"ERROR: {p} not found. Run `python main.py` first.")
    sys.exit(1)

df = pd.read_csv(p)
n = len(df)
n_ok = df["error"].isna().sum() if "error" in df.columns else n
print(f"Loaded {n} rows from {p}")
print(f"Rows without fetch error: {n_ok}\n")

# Fields we care about, grouped by parser source
FIELD_GROUPS = {
    "TOP RATIOS (parsed from top-of-page)": [
        "market_cap_cr", "current_price", "pe_ratio", "book_value",
        "price_to_book", "roe", "roce", "dividend_yield", "high_52w", "low_52w",
    ],
    "SHAREHOLDING (parsed from shareholding table)": [
        "promoter_holding", "promoter_pledge", "fii_holding",
        "dii_holding", "public_holding",
    ],
    "GROWTH RATES (parsed from compounded-growth tables)": [
        "sales_growth_5y", "sales_growth_3y", "sales_growth_ttm",
        "profit_growth_5y", "profit_growth_3y", "profit_growth_ttm",
    ],
    "P&L / RATIOS TABLES": [
        "operating_margin", "profit_margin", "debt_to_equity",
    ],
}

# Only count rows that fetched OK
successful = df[df["error"].isna()] if "error" in df.columns else df
denom = len(successful) or 1

print("=" * 70)
print("FIELD COVERAGE (across successfully-fetched tickers)")
print("=" * 70)

any_broken = False
for group_name, fields in FIELD_GROUPS.items():
    print(f"\n[{group_name}]")
    for f in fields:
        if f not in successful.columns:
            print(f"  {f:26s} MISSING FROM CSV — parser never wrote this field")
            any_broken = True
            continue
        n_present = successful[f].notna().sum()
        pct = n_present / denom * 100
        flag = ""
        if pct < 30:
            flag = "  ← BROKEN (parser not finding this)"
            any_broken = True
        elif pct < 80:
            flag = "  ← PARTIAL"
        print(f"  {f:26s} {n_present:4d}/{denom} ({pct:5.1f}%){flag}")

# Show which errors occurred if fetches failed
if "error" in df.columns:
    errs = df[df["error"].notna()]["error"]
    if len(errs):
        print(f"\n{'=' * 70}")
        print(f"FETCH ERRORS ({len(errs)} tickers)")
        print("=" * 70)
        for err, count in errs.value_counts().head(5).items():
            print(f"  ({count}x) {err[:100]}")

# Show a few sample rows so we can eyeball actual values
print(f"\n{'=' * 70}")
print("SAMPLE — first 3 tickers with data (key fields)")
print("=" * 70)
sample_cols = ["symbol", "name", "market_cap_cr", "roe", "roce",
               "operating_margin", "debt_to_equity",
               "sales_growth_5y", "profit_growth_5y",
               "promoter_holding", "promoter_pledge"]
sample_cols = [c for c in sample_cols if c in successful.columns]
with pd.option_context("display.width", 200, "display.max_columns", None,
                        "display.max_colwidth", 25):
    print(successful[sample_cols].head(3).to_string(index=False))

# Verdict
print(f"\n{'=' * 70}")
print("VERDICT")
print("=" * 70)
if any_broken:
    print("Some parsers are not finding their target fields. Fix needed in src/fetch.py.")
    print("Share this output with the copilot to identify which parsers to fix.")
else:
    print("All parsers extracted reasonable coverage. If filter still returns 0,")
    print("thresholds may be too strict — try `python main.py --skip-fundamentals --permissive`")
