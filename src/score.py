"""
Composite factor scoring for India — includes an India-unique Promoter Signal.

Weights favour financial strength AND governance (promoter alignment) —
key differences from the US screener:

  Quality        30%  (same as US)
  Health         25%  (same as US)
  Growth         20%  (down from 25% — Indian small caps have volatile growth)
  Promoter       15%  (NEW — India-specific: promoter holding + inverse of pledge)
  Valuation      10%  (down from 15% — Indian growth stocks routinely trade at high P/Es)
  Momentum       0%   (removed — not a fundamental signal; we have technical score for entry timing)

The promoter signal captures the two most predictive India-specific factors:
  * High promoter holding (aligned interests, skin in the game)
  * Low or zero pledge (no forced-selling / margin call risk)

A company with 70% promoter holding, 0% pledge is a much stronger multibagger
setup than one with 25% holding and 30% pledge, all else equal.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

DEFAULT_WEIGHTS = {
    "quality":   0.30,
    "health":    0.25,
    "growth":    0.20,
    "promoter":  0.15,   # India-specific governance signal
    "valuation": 0.10,
    "momentum":  0.00,
}

FACTOR_KEYS = ["quality", "growth", "health", "promoter", "valuation"]


# ------------------------------------------------------------------ #
# Robust z-score
# ------------------------------------------------------------------ #

def _robust_z(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    med = s.median()
    mad = (s - med).abs().median()
    if pd.isna(mad) or mad == 0:
        return pd.Series(0.0, index=series.index)
    z = (s - med) / (1.4826 * mad)
    return z.clip(-3, 3).fillna(0)


def _safe_mean(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    present = [c for c in cols if c in df.columns]
    if not present:
        return pd.Series(0.0, index=df.index)
    z = df[present].apply(_robust_z)
    return z.mean(axis=1)


# ------------------------------------------------------------------ #
# 0-10 scale conversion
# ------------------------------------------------------------------ #

def _to_multibagger_10(composite: pd.Series) -> pd.Series:
    n = len(composite)
    if n == 0:
        return composite
    if n == 1:
        return pd.Series([10.0], index=composite.index)
    ranks = composite.rank(ascending=True, method="min")
    percentile = (ranks - 1) / (n - 1)
    return (5.0 + 5.0 * percentile).round(1)


# ------------------------------------------------------------------ #
# Rationale generation
# ------------------------------------------------------------------ #

def _cap_first(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _fmt_num(x, suffix="%"):
    """Format a percentage-style number (screener values are already % form: 15.0 means 15%)."""
    if pd.isna(x):
        return None
    return f"{x:.0f}{suffix}"


def _describe_strength(key: str, row: pd.Series) -> str:
    if key == "quality":
        bits = []
        if (v := _fmt_num(row.get("roe"))) is not None:                bits.append(f"ROE {v}")
        if (v := _fmt_num(row.get("roce"))) is not None:               bits.append(f"ROCE {v}")
        if not bits and (v := _fmt_num(row.get("operating_margin"))) is not None:
            bits.append(f"OPM {v}")
        detail = f" ({', '.join(bits)})" if bits else ""
        return f"strong profitability{detail}"

    if key == "growth":
        bits = []
        if (v := _fmt_num(row.get("sales_growth_5y"))) is not None:    bits.append(f"5y sales {v}")
        if (v := _fmt_num(row.get("profit_growth_5y"))) is not None:   bits.append(f"5y profit {v}")
        detail = f" ({', '.join(bits)})" if bits else ""
        return f"solid growth{detail}"

    if key == "health":
        bits = []
        de = row.get("debt_to_equity")
        if pd.notna(de): bits.append(f"D/E {de:.2f}")
        detail = f" ({', '.join(bits)})" if bits else ""
        return f"healthy balance sheet{detail}"

    if key == "promoter":
        bits = []
        ph = row.get("promoter_holding")
        pp = row.get("promoter_pledge")
        if pd.notna(ph): bits.append(f"promoter {ph:.0f}%")
        if pd.notna(pp): bits.append(f"pledge {pp:.0f}%")
        detail = f" ({', '.join(bits)})" if bits else ""
        return f"strong promoter alignment{detail}"

    if key == "valuation":
        bits = []
        pe = row.get("pe_ratio")
        pb = row.get("price_to_book")
        if pd.notna(pe) and pe > 0:   bits.append(f"P/E {pe:.0f}")
        if pd.notna(pb) and pb > 0:   bits.append(f"P/B {pb:.1f}")
        detail = f" ({', '.join(bits)})" if bits else ""
        return f"reasonable valuation{detail}"

    return f"strong {key}"


def _describe_weakness(key: str, row: pd.Series) -> str:
    if key == "quality":   return "profitability is the softer spot"
    if key == "growth":    return "growth is modest — more of a compounder"
    if key == "health":    return "balance sheet worth monitoring"
    if key == "promoter":  return "promoter signal is average (moderate holding or some pledge)"
    if key == "valuation": return "valuation looks stretched"
    return f"{key} lags peers"


def _generate_rationale(row: pd.Series) -> str:
    scores = {k: row.get(f"{k}_score", 0) for k in FACTOR_KEYS}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top1_key = ranked[0][0]
    top2_key = ranked[1][0]
    weak_key = ranked[-1][0]

    s1 = _cap_first(_describe_strength(top1_key, row))
    s2 = _describe_strength(top2_key, row)
    w  = _cap_first(_describe_weakness(weak_key, row))
    return f"{s1}; {s2}. {w}."


# ------------------------------------------------------------------ #
# Main scoring
# ------------------------------------------------------------------ #

def compute_scores(df: pd.DataFrame, weights: dict | None = None) -> pd.DataFrame:
    """
    Compute all factor sub-scores + composite + Multibagger Score + rationale.
    Returns df sorted descending by multibagger_score.
    """
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    df = df.copy()

    # QUALITY: profitability + capital efficiency
    df["quality_score"] = _safe_mean(df, [
        "roe", "roce", "operating_margin", "profit_margin",
    ])

    # GROWTH: prefer longer-term CAGRs (more stable than TTM)
    df["growth_score"] = _safe_mean(df, [
        "sales_growth_5y", "sales_growth_3y", "sales_growth_ttm",
        "profit_growth_5y", "profit_growth_3y", "profit_growth_ttm",
    ])

    # HEALTH: lower D/E is better → invert
    if "debt_to_equity" in df.columns:
        df["health_score"] = -_robust_z(df["debt_to_equity"])
    else:
        df["health_score"] = 0.0

    # PROMOTER: high holding + LOW pledge (invert pledge)
    prom_z = _robust_z(df["promoter_holding"]) if "promoter_holding" in df.columns else pd.Series(0.0, index=df.index)
    pledge_z = -_robust_z(df["promoter_pledge"]) if "promoter_pledge" in df.columns else pd.Series(0.0, index=df.index)
    df["promoter_score"] = (prom_z + pledge_z) / 2

    # VALUATION: lower multiples better (invert), but ignore negatives
    val_z = pd.DataFrame(index=df.index)
    for col in ["pe_ratio", "price_to_book"]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").where(lambda x: x > 0)
            val_z[col] = -_robust_z(s)
    df["valuation_score"] = val_z.mean(axis=1).fillna(0) if len(val_z.columns) else pd.Series(0.0, index=df.index)

    # No momentum score here — kept out of fundamentals; technical_score covers entry timing

    # COMPOSITE
    df["composite_score"] = (
        weights["quality"]   * df["quality_score"] +
        weights["growth"]    * df["growth_score"] +
        weights["health"]    * df["health_score"] +
        weights["promoter"]  * df["promoter_score"] +
        weights["valuation"] * df["valuation_score"]
    )

    df["multibagger_score"] = _to_multibagger_10(df["composite_score"])
    df = df.sort_values("multibagger_score", ascending=False).reset_index(drop=True)
    df["rationale"] = df.apply(_generate_rationale, axis=1)

    return df
