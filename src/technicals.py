"""
Technical analysis for India — same math as US screener, but yfinance
tickers get the `.NS` suffix (NSE) for the price fetch.

Sequential fetch with polite delays to avoid Yahoo rate limits.

Computes per ticker:
  * RSI (14-day, Wilder smoothing)
  * 50-day and 200-day moving averages
  * Distance from 200-day MA and 52-week high
  * Supertrend DAILY (ATR period=10, multiplier=2.5) — short-term signal
  * Supertrend WEEKLY (daily bars resampled to weekly) — long-term trend
  * Technical Score (0-10): "how good is this entry point?"
"""
from __future__ import annotations
import time
import warnings
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from src.supertrend import calculate_supertrend

warnings.filterwarnings("ignore")

ATR_PERIOD = 10
ATR_MULTIPLIER = 2.5
LOOKBACK_PERIOD = "3y"
INTERVAL = "1d"
FETCH_DELAY = 0.5
RATE_LIMIT_WAIT = 15
MIN_BARS_REQUIRED = 60
MIN_WEEKLY_BARS = 15


# ------------------------------------------------------------------ #
# Indicators (identical to US version)
# ------------------------------------------------------------------ #

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_technical_score(
    rsi_val: float | None, price: float, ma_200: float | None,
    high_52w: float, low_52w: float,
) -> float:
    score = 5.0

    if rsi_val is not None and not pd.isna(rsi_val):
        if 40 <= rsi_val <= 60:      score += 2.0
        elif 30 <= rsi_val < 40:     score += 1.5
        elif 60 < rsi_val <= 70:     score += 0.5
        elif rsi_val > 70:           score -= 2.0
        elif 20 <= rsi_val < 30:     score += 0.5
        elif rsi_val < 20:           score -= 1.0

    if ma_200 is not None and not pd.isna(ma_200) and ma_200 > 0:
        pct = (price - ma_200) / ma_200
        if 0.05 <= pct <= 0.20:      score += 1.5
        elif 0 <= pct < 0.05:        score += 1.0
        elif 0.20 < pct <= 0.40:     score += 0.0
        elif pct > 0.40:             score -= 1.5
        elif -0.10 <= pct < 0:       score -= 0.5
        elif pct < -0.10:            score -= 1.5

    if not pd.isna(high_52w) and high_52w > 0:
        pct_from_high = (high_52w - price) / high_52w
        if 0.10 <= pct_from_high <= 0.25:      score += 1.5
        elif 0.05 <= pct_from_high < 0.10:     score += 0.5
        elif pct_from_high < 0.05:             score -= 1.0
        elif 0.25 < pct_from_high <= 0.40:     score += 0.5
        elif pct_from_high > 0.40:             score -= 0.5

    return max(0.0, min(10.0, round(score, 1)))


def _supertrend_state(hist: pd.DataFrame) -> tuple[str | None, int | None]:
    st_df = calculate_supertrend(hist, period=ATR_PERIOD, multiplier=ATR_MULTIPLIER)
    st_df = st_df.dropna(subset=["Supertrend"])
    if len(st_df) < 2:
        return None, None

    direction_now = int(st_df.iloc[-1]["Direction"])
    signal = "BUY" if direction_now == 1 else "SELL"

    dirs = st_df["Direction"].values
    bars_in_trend = 1
    for i in range(len(dirs) - 2, -1, -1):
        if dirs[i] == direction_now:
            bars_in_trend += 1
        else:
            break
    return signal, bars_in_trend


def _daily_to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    weekly = daily.resample("W-FRI", label="right").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna(subset=["High", "Low", "Close"])
    return weekly


# ------------------------------------------------------------------ #
# Fetch with .NS suffix (NSE)
# ------------------------------------------------------------------ #

def _fetch_history(symbol: str, retries: int = 1) -> tuple[pd.DataFrame | None, str]:
    """
    Fetch 3y of daily OHLC from yfinance. Appends `.NS` suffix for NSE tickers.
    Retries once on rate limit.
    """
    yf_ticker = f"{symbol}.NS"
    for attempt in range(retries + 1):
        try:
            data = yf.Ticker(yf_ticker).history(
                period=LOOKBACK_PERIOD,
                interval=INTERVAL,
                auto_adjust=False,
            )
            if data is None or data.empty:
                return None, "no data returned"
            data = data.dropna(subset=["High", "Low", "Close"])
            if len(data) < MIN_BARS_REQUIRED:
                return None, f"only {len(data)} bars (need {MIN_BARS_REQUIRED}+)"
            return data, ""
        except Exception as e:
            err_str = f"{type(e).__name__}: {str(e)[:100]}"
            is_rate_limit = ("rate limit" in str(e).lower()
                             or "too many requests" in str(e).lower()
                             or "429" in str(e))
            if is_rate_limit and attempt < retries:
                print(f"    [{symbol}] rate limit hit, waiting {RATE_LIMIT_WAIT}s and retrying...")
                time.sleep(RATE_LIMIT_WAIT)
                continue
            return None, err_str
    return None, "rate limit persisted after retries"


def _compute_indicators(symbol: str, hist: pd.DataFrame) -> dict[str, Any]:
    close = hist["Close"]

    current_price = float(close.iloc[-1])

    rsi_series = rsi(close)
    rsi_val = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None

    ma_50 = close.rolling(50).mean().iloc[-1]
    ma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else np.nan
    ma_50_v = float(ma_50) if not pd.isna(ma_50) else None
    ma_200_v = float(ma_200) if not pd.isna(ma_200) else None

    last_252 = close.tail(252)
    high_52w = float(last_252.max())
    low_52w = float(last_252.min())

    pct_from_200ma = ((current_price - ma_200_v) / ma_200_v * 100) if ma_200_v else None
    pct_from_52w_high = ((high_52w - current_price) / high_52w * 100) if high_52w > 0 else None

    # Daily Supertrend
    daily_signal, daily_bars = _supertrend_state(hist)

    # Weekly Supertrend (resampled)
    weekly_hist = _daily_to_weekly(hist)
    if len(weekly_hist) >= MIN_WEEKLY_BARS:
        weekly_signal, weekly_bars = _supertrend_state(weekly_hist)
    else:
        weekly_signal, weekly_bars = None, None

    tech_score = compute_technical_score(rsi_val, current_price, ma_200_v, high_52w, low_52w)

    return {
        "symbol": symbol,
        "technical_error": None,
        "current_price_yf": round(current_price, 2),
        "rsi_14": round(rsi_val, 1) if rsi_val is not None else None,
        "ma_50": round(ma_50_v, 2) if ma_50_v else None,
        "ma_200": round(ma_200_v, 2) if ma_200_v else None,
        "pct_from_200ma": round(pct_from_200ma, 1) if pct_from_200ma is not None else None,
        "pct_from_52w_high": round(pct_from_52w_high, 1) if pct_from_52w_high is not None else None,
        "technical_score": tech_score,
        "supertrend_daily_signal": daily_signal,
        "supertrend_daily_days": daily_bars,
        "supertrend_weekly_signal": weekly_signal,
        "supertrend_weekly_weeks": weekly_bars,
    }


def fetch_technicals(symbols: list[str], **_kwargs) -> pd.DataFrame:
    """
    Sequential yfinance fetch + indicator computation for NSE tickers.
    Each `symbol` is a bare NSE symbol (no `.NS` suffix) — added internally.
    """
    n = len(symbols)
    print(f"Fetching technicals for {n} candidates via yfinance (.NS), sequential {FETCH_DELAY}s delay")

    results: list[dict[str, Any]] = []
    t0 = time.time()

    for i, symbol in enumerate(symbols, 1):
        hist, err = _fetch_history(symbol)
        if hist is None:
            results.append({"symbol": symbol, "technical_error": err})
            status = f"failed: {err[:40]}"
        else:
            try:
                results.append(_compute_indicators(symbol, hist))
                status = "ok"
            except Exception as e:
                err = f"compute: {type(e).__name__}: {str(e)[:80]}"
                results.append({"symbol": symbol, "technical_error": err})
                status = f"failed: {err[:40]}"

        if i % 10 == 0 or i == n:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed else 0
            eta = (n - i) / rate if rate else 0
            print(f"  {i}/{n} · last: {symbol} → {status} · {elapsed:.0f}s elapsed · ETA {eta:.0f}s")

        if i < n:
            time.sleep(FETCH_DELAY)

    df = pd.DataFrame(results)
    n_ok = df["technical_error"].isna().sum() if "technical_error" in df.columns else 0
    print(f"\nTechnicals success: {n_ok}/{n} ({n_ok/n*100:.0f}%)")

    if n_ok < n * 0.8 and "technical_error" in df.columns:
        errs = df[df["technical_error"].notna()]["technical_error"]
        print("Sample errors (top 3 unique):")
        for err, count in errs.value_counts().head(3).items():
            print(f"  ({count}x) {err[:140]}")

    return df
