# 🇮🇳 India Multibagger Screener

Factor-based screener that ranks Indian mid- and small-cap stocks (NSE Nifty
Midcap 150 + Smallcap 250) by their fit to a multibagger profile — with
India-specific quality signals (**promoter holding, promoter pledge**) that
matter far more here than in US markets.

**Free**. No paid APIs. Runs locally and on GitHub Actions.

---

## What this does

1. **Universe** — Fetches ~400 tickers from NSE Nifty Midcap 150 + Nifty Smallcap 250 (excludes Nifty 50 large caps which are too big to plausibly 10x).
2. **Fundamentals** — Scrapes [screener.in](https://www.screener.in) for each ticker — the site of choice for Indian equity analysis. Extracts:
   - Financial ratios (P/E, ROE, ROCE, D/E, OPM, book value)
   - Multi-year growth (5y / 3y / TTM CAGRs for sales & profit)
   - **Shareholding pattern** (promoter %, pledged %, FII, DII)
3. **Filter** — India-specific hard filters (see below).
4. **Multibagger Score (0-10)** — weighted composite with an India-specific **Promoter** factor.
5. **Cooldown** — 60s pause to let Yahoo rate limits reset before phase 2.
6. **Technicals** — Fetches 3 years of daily price history via yfinance (with `.NS` suffix), computes:
   - RSI (14-day)
   - 50/200-day moving averages
   - Supertrend on both **daily** and **weekly** candles (BUY / SELL signals)
   - Technical Score (0-10) — "how good is this entry point?"
7. **HTML report** — interactive sortable table published to GitHub Pages.

---

## Why India needs its own screener

The multibagger factor model that works for US large-caps doesn't fit
Indian mid/small caps well. Three big differences:

| Factor | US screener | India screener |
|--------|-------------|-----------------|
| Governance | Not really needed | **Critical** — promoter pledge/holding is the #1 predictor of both blowups AND compounders |
| Valuation weight | 15% | 10% (Indian growth stocks routinely trade at high P/Es) |
| Quality bar | ROE ≥12% | ROE ≥15% + ROCE ≥15% (wider dispersion, filter harder) |
| Debt tolerance | D/E ≤1.5 | D/E ≤1.0 (Indian debt-fuelled collapses are more common) |
| Data source | yfinance | **screener.in** (better fundamentals + governance data) |

---

## Quick start (local)

Python 3.10+ required.

```bash
git clone https://github.com/<your-username>/multibagger-screener-india.git
cd multibagger-screener-india

python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows

pip install -r requirements.txt

# Smoke test (~20 tickers, ~90 seconds)
python main.py --sample

# Open the report
open output/index.html       # macOS
start output/index.html      # Windows
```

If the sample works, do a real run:

```bash
python main.py --limit 100   # ~4 min
python main.py               # full ~400 tickers, 10-15 min
```

---

## CLI flags

| Flag | Purpose |
|------|---------|
| `--sample` | ~20 hand-picked tickers, useful for smoke tests |
| `--limit N` | First N tickers of the universe (for iteration) |
| `--midcap-only` | Only Nifty Midcap 150 |
| `--smallcap-only` | Only Nifty Smallcap 250 |
| `--permissive` | Include rows with missing data |
| `--top N` | Show top N in HTML report (default 50) |
| `--wait-before-technicals N` | Cooldown seconds before technicals (default 60) |
| `--skip-fundamentals` | Reuse cached scored.csv (retry technicals only) |
| `--skip-technicals` | Fundamentals-only report |

---

## Project layout

```
multibagger-screener-india/
├── main.py                     # Entry point
├── requirements.txt
├── README.md
├── src/
│   ├── universe.py             # NSE index constituents
│   ├── fetch.py                # screener.in scraping
│   ├── screen.py               # Filters (India-specific)
│   ├── score.py                # Multibagger scoring + rationale
│   ├── technicals.py           # yfinance (.NS) + Supertrend
│   ├── supertrend.py           # Indicator math
│   └── report.py               # HTML (₹/Cr formatting)
├── .github/workflows/
│   └── screener.yml            # Weekly automated run
└── output/                     # Generated CSVs + index.html
```

---

## Filters (edit in `src/screen.py`)

```python
DEFAULT_FILTERS = {
    "market_cap_min_cr": 1_000,        # ₹1,000 Cr (~$120M)
    "market_cap_max_cr": 40_000,       # ₹40,000 Cr (~$4.8B)
    "roe_min": 15.0,                   # 15% ROE
    "roce_min": 15.0,                  # 15% ROCE
    "operating_margin_min": 10.0,      # 10% OPM
    "sales_growth_5y_min": 10.0,       # 10% CAGR sales
    "profit_growth_5y_min": 10.0,      # 10% CAGR profit
    "debt_to_equity_max": 1.0,
    "promoter_holding_min": 30.0,      # 30% promoter stake
    "promoter_pledge_max": 10.0,       # <10% pledge (0 is ideal)
}
```

## Scoring weights (edit in `src/score.py`)

```python
DEFAULT_WEIGHTS = {
    "quality":   0.30,   # ROE, ROCE, OPM, profit margin
    "health":    0.25,   # Debt/Equity (inverse)
    "growth":    0.20,   # Multi-year CAGRs
    "promoter":  0.15,   # India-specific: holding - pledge
    "valuation": 0.10,   # P/E, P/B (inverse — lower is better)
}
```

---

## How to read the report

Each candidate gets three independent signals:

**Multibagger Score (0-10)** — fundamental quality. Higher = better multibagger candidate.

**Technical Score (0-10)** — entry-point quality. High MB + high Tech = ready to buy. High MB + low Tech = great business but overextended, wait.

**Supertrend (Weekly + Daily)** — trend confirmation:

| Weekly | Daily | Setup |
|--------|-------|-------|
| 🟢 BUY (30w) | 🟢 BUY (12d) | Strongest — all timeframes aligned bullish |
| 🟢 BUY (28w) | 🔴 SELL (2d) | Pullback in uptrend — possible entry |
| 🔴 SELL (8w) | 🟢 BUY (5d) | Dead-cat bounce risk — be cautious |
| 🔴 SELL | 🔴 SELL | Avoid — all timeframes bearish |

The **Promoter** column shows total promoter holding %. Higher is better (aligned interests).

The **Pledge** column shows promoter pledge %. Zero is ideal; >10% is a warning; >20% is a red flag.

---

## Pushing to GitHub + enabling Pages

```bash
git init
git add .
git commit -m "Initial India multibagger screener"
git branch -M main
git remote add origin https://github.com/<your-username>/multibagger-screener-india.git
git push -u origin main
```

Then:

1. **Settings → Actions → General → Workflow permissions → Read and write permissions** → Save
2. Trigger a run: **Actions → Weekly Multibagger Screener (India) → Run workflow** with `limit: 50` for a quick test.
3. Wait for it to finish. This creates the `gh-pages` branch.
4. **Settings → Pages → Source: Deploy from a branch → Branch: `gh-pages` / `/ (root)`** → Save.
5. Report lives at `https://<your-username>.github.io/multibagger-screener-india/`.

Weekly schedule runs every Saturday 06:00 UTC (after Friday IST close).

---

## Honest caveats

- **Screener.in has no formal API.** We scrape public pages politely (sequential, 0.7s delays, browser headers). This works reliably in practice but could break if screener.in changes its HTML structure — parsers are defensive but not bulletproof.
- **Governance risk isn't fully captured** even with promoter/pledge filters. Auditor changes, related-party transactions, and management background require manual review before acting on any name.
- **Data quality varies.** Some small caps have missing fields on screener.in (especially newer listings). Strict mode excludes them; permissive mode keeps them with holes.
- **Multibagger identification is inherently probabilistic.** Even a 10/10 candidate is a research starting point, not a buy signal.

---

## Disclaimer

For **educational and research purposes only**. Nothing here is investment
advice. Indian small caps in particular carry significant governance and
liquidity risks. You are solely responsible for your investment decisions.
