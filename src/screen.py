"""
Hard filters for India-specific multibagger screening.

Two India-specific filters that don't exist in the US version:
  * Promoter Holding — >30% preferred (strong promoter stake = aligned interests)
  * Promoter Pledge — <10% required (pledge is the biggest red flag in Indian equities)

Thresholds are stricter than US because Indian small caps have wider
quality dispersion and more fraud/governance risk.
"""
from __future__ import annotations
import pandas as pd

# All monetary values in ₹ Crores. All percentages as % (e.g. 15 for 15%, not 0.15)
DEFAULT_FILTERS = {
    # Growth runway (in ₹ Crores)
    "market_cap_min_cr": 1_000,          # ₹1,000 Cr (~$120M)
    "market_cap_max_cr": 40_000,         # ₹40,000 Cr (~$4.8B) — above this, 10x is rare

    # Quality (stricter than US)
    "roe_min": 15.0,                     # 15% (US uses 12%)
    "roce_min": 15.0,                    # Indian analysts prefer ROCE over ROA
    "operating_margin_min": 10.0,        # 10% OPM

    # Growth
    "sales_growth_5y_min": 10.0,         # 10% 5y CAGR sales growth
    "profit_growth_5y_min": 10.0,        # 10% 5y CAGR profit growth (positive earnings)

    # Financial health (tighter than US)
    "debt_to_equity_max": 1.0,           # ratio (US uses 1.5)

    # India-specific (governance)
    "promoter_holding_min": 30.0,        # 30% promoter stake — aligned interests
    "promoter_pledge_max": 10.0,         # <10% pledge (0 is ideal; >20% is a big red flag)
}


def apply_filters(
    df: pd.DataFrame,
    cfg: dict | None = None,
    strict: bool = True,
) -> pd.DataFrame:
    """
    Apply hard filters. Returns rows that pass all checks + a 'passed_filters' flag.

    strict=True (default): missing values fail the filter. Safer for India where
                           missing data often indicates weak reporting.
    strict=False: missing values pass. Larger, noisier candidate pool.
    """
    cfg = {**DEFAULT_FILTERS, **(cfg or {})}
    n_start = len(df)
    print(f"\nApplying filters to {n_start} rows...")

    fail_val = 999 if strict else 0  # for max-thresholds, high value fails
    pass_val = -999 if strict else 999  # for min-thresholds, low value fails in strict

    def _min_check(col, threshold):
        if col not in df.columns:
            return pd.Series(True, index=df.index) if not strict else pd.Series(False, index=df.index)
        return df[col].fillna(pass_val) >= threshold

    def _max_check(col, threshold):
        if col not in df.columns:
            return pd.Series(True, index=df.index) if not strict else pd.Series(False, index=df.index)
        return df[col].fillna(fail_val) <= threshold

    checks = []

    # Market cap band (both min and max)
    if "market_cap_cr" in df.columns:
        c = df["market_cap_cr"].fillna(0).between(cfg["market_cap_min_cr"], cfg["market_cap_max_cr"])
        checks.append(("market_cap_band", c))

    checks.append(("roe_min",              _min_check("roe", cfg["roe_min"])))
    checks.append(("roce_min",             _min_check("roce", cfg["roce_min"])))
    checks.append(("operating_margin_min", _min_check("operating_margin", cfg["operating_margin_min"])))
    checks.append(("sales_growth_5y_min",  _min_check("sales_growth_5y", cfg["sales_growth_5y_min"])))
    checks.append(("profit_growth_5y_min", _min_check("profit_growth_5y", cfg["profit_growth_5y_min"])))
    checks.append(("debt_to_equity_max",   _max_check("debt_to_equity", cfg["debt_to_equity_max"])))
    checks.append(("promoter_holding_min", _min_check("promoter_holding", cfg["promoter_holding_min"])))
    checks.append(("promoter_pledge_max",  _max_check("promoter_pledge", cfg["promoter_pledge_max"])))

    # Report per-filter pass rate
    print("Per-filter pass rate:")
    combined = pd.Series(True, index=df.index)
    for name, check in checks:
        n_pass = check.sum()
        print(f"  {name:24s}: {n_pass:4d}/{n_start} pass ({n_pass/n_start*100:.1f}%)")
        combined &= check

    passed = df[combined].copy()
    passed["passed_filters"] = True
    print(f"\nAll filters combined: {len(passed)}/{n_start} pass ({len(passed)/n_start*100:.1f}%)")
    return passed.reset_index(drop=True)
