"""
Hard filters for India-specific multibagger screening.

Two India-specific filters that don't exist in the US version:
  * Promoter Holding — >30% preferred (strong promoter stake = aligned interests)
  * Promoter Pledge — <10% required (pledge is the biggest red flag in Indian equities)

Diagnostic behaviour:
  * Reports per-filter pass rate AND breaks down failures into
    "missing value" vs "below/above threshold" so you can see whether
    filters are failing due to bad data or genuinely poor companies.
  * strict=False (permissive) is the DEFAULT now — treating missing
    values as "unknown, let it pass" prevents silent wipeouts when a
    parser breaks. Use strict=True if you want to enforce coverage.
"""
from __future__ import annotations
import pandas as pd

# Values in ₹ Crores. Percentages as % (e.g. 15 for 15%, not 0.15)
DEFAULT_FILTERS = {
    "market_cap_min_cr": 1_000,
    "market_cap_max_cr": 40_000,
    "roe_min": 15.0,
    "roce_min": 15.0,
    "operating_margin_min": 10.0,
    "sales_growth_5y_min": 10.0,
    "profit_growth_5y_min": 10.0,
    "debt_to_equity_max": 1.0,
    "promoter_holding_min": 30.0,
    "promoter_pledge_max": 10.0,
}


def _check_min(df: pd.DataFrame, col: str, threshold: float, strict: bool):
    """
    Return (pass_mask, n_missing) where pass_mask is True for rows that
    either have value >= threshold, or (in non-strict mode) have missing value.
    """
    if col not in df.columns:
        # Field doesn't exist at all — treat as all-missing
        mask = pd.Series(not strict, index=df.index)  # pass if permissive
        return mask, len(df)
    s = df[col]
    is_missing = s.isna()
    passes_threshold = s >= threshold  # NaN >= x returns False (not NaN)
    if strict:
        mask = passes_threshold & ~is_missing  # explicit: missing → False
    else:
        mask = passes_threshold | is_missing   # explicit: missing → True
    return mask, int(is_missing.sum())


def _check_max(df: pd.DataFrame, col: str, threshold: float, strict: bool):
    if col not in df.columns:
        mask = pd.Series(not strict, index=df.index)
        return mask, len(df)
    s = df[col]
    is_missing = s.isna()
    passes_threshold = s <= threshold
    if strict:
        mask = passes_threshold & ~is_missing
    else:
        mask = passes_threshold | is_missing
    return mask, int(is_missing.sum())


def _check_range(df: pd.DataFrame, col: str, lo: float, hi: float, strict: bool):
    if col not in df.columns:
        mask = pd.Series(not strict, index=df.index)
        return mask, len(df)
    s = df[col]
    is_missing = s.isna()
    passes_threshold = s.between(lo, hi)
    if strict:
        mask = passes_threshold & ~is_missing
    else:
        mask = passes_threshold | is_missing
    return mask, int(is_missing.sum())


def apply_filters(
    df: pd.DataFrame,
    cfg: dict | None = None,
    strict: bool = False,
) -> pd.DataFrame:
    """
    Apply hard filters with clear diagnostics.

    Parameters
    ----------
    df : DataFrame from fetch_fundamentals()
    cfg : dict of thresholds, falls back to DEFAULT_FILTERS
    strict : True = missing values FAIL the filter. False (default) = missing
             values PASS the filter (so a broken parser doesn't wipe you out).

    Report format:
      filter_name             : PPP/TTT pass (XX%) [missing YY]
    where PPP is pass count, TTT is total, XX% is pass rate, YY is how many
    rows had missing values for that field (and thus contributed to the failure
    count in strict mode, or slipped through in permissive mode).
    """
    cfg = {**DEFAULT_FILTERS, **(cfg or {})}
    n_start = len(df)
    mode = "STRICT (missing=fail)" if strict else "PERMISSIVE (missing=pass)"
    print(f"\nApplying filters to {n_start} rows [{mode}]...")

    checks = [
        ("market_cap_band",
         _check_range(df, "market_cap_cr", cfg["market_cap_min_cr"], cfg["market_cap_max_cr"], strict)),
        ("roe_min",
         _check_min(df, "roe", cfg["roe_min"], strict)),
        ("roce_min",
         _check_min(df, "roce", cfg["roce_min"], strict)),
        ("operating_margin_min",
         _check_min(df, "operating_margin", cfg["operating_margin_min"], strict)),
        ("sales_growth_5y_min",
         _check_min(df, "sales_growth_5y", cfg["sales_growth_5y_min"], strict)),
        ("profit_growth_5y_min",
         _check_min(df, "profit_growth_5y", cfg["profit_growth_5y_min"], strict)),
        ("debt_to_equity_max",
         _check_max(df, "debt_to_equity", cfg["debt_to_equity_max"], strict)),
        ("promoter_holding_min",
         _check_min(df, "promoter_holding", cfg["promoter_holding_min"], strict)),
        ("promoter_pledge_max",
         _check_max(df, "promoter_pledge", cfg["promoter_pledge_max"], strict)),
    ]

    print("Per-filter pass rate:")
    combined = pd.Series(True, index=df.index)
    for name, (mask, n_missing) in checks:
        n_pass = int(mask.sum())
        missing_note = f" [missing {n_missing}]" if n_missing else ""
        print(f"  {name:24s}: {n_pass:4d}/{n_start} pass ({n_pass/n_start*100:5.1f}%){missing_note}")
        combined &= mask

    passed = df[combined].copy()
    passed["passed_filters"] = True
    n_pass = len(passed)
    print(f"\nAll filters combined: {n_pass}/{n_start} pass ({n_pass/n_start*100:.1f}%)")

    if n_pass == 0:
        print("\n  ZERO candidates passed all filters.")
        print("  Diagnostics:")
        print("  1. Check per-filter rates above — a filter at 0% pass is usually the culprit")
        print("     (either the parser isn't extracting that field, or thresholds are too strict)")
        print("  2. Run `python diagnose.py` to see full field coverage")
        print("  3. Try `--permissive` (should already be default now) to let missing fields pass")
        print("  4. Edit DEFAULT_FILTERS in src/screen.py to relax specific thresholds")

    return passed.reset_index(drop=True)
