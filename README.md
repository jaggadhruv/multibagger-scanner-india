# India Multibagger Shortlist

A weekly screen of Indian mid and small caps that returns a short list, not a ranking.
A stock is shown only if it clears a fixed 12-point checklist: a business that has
already proven itself, is still inflecting, and whose chart is confirming it.

Fundamentals come from screener.in company pages, prices from Yahoo Finance (`.NS`).
Free data only, no API keys, no secrets.

## What changed from the old version

| Old | New |
|---|---|
| Scored stocks against each other, so someone always got 10/10 | Every check is a fixed yes or no. Zero stocks in a week is a valid result |
| Missing data counted as a pass | Missing data counts as not met, and is reported loudly |
| Filters on debt/equity and pledge, which the page does not show | Debt/equity is computed from the balance sheet; pledge is read from the page's Cons list |
| Parser tied to page layout | Tables are recognised by their row labels |
| Chart data shown but ignored in ranking | Chart is a gate. No uptrend, no tier A |
| No record of results | Every pick is logged and measured against the Nifty 50 |

The old version returned an empty list in strict mode because two of its filters
(debt/equity and promoter pledge) looked for fields that do not exist on the public
screener.in page, so every company failed them.

## The checklist

**Gate 1, proven business** (all seven required)

1. Sales growth of 15%+ a year over 3 years
2. Sales up in each of the last 3 years
3. ROCE of 20%+, 3-year average
4. Operating cash flow positive in at least 3 of the last 4 years
5. Operating cash flow at least 70% of net profit over 3 years
6. Borrowings no more than 0.6x shareholders' funds
7. Promoters hold 30%+, have not sold more than 3 points in a year, no pledge above 5% flagged

**Gate 2, early / inflecting** (both required)

8. Operating margin higher than 3 years ago, and not rolling over
9. Growth holding up: latest year and latest quarter not fading

**Gate 3, chart strength** (all three required, two routes)

10. Weekly Supertrend on BUY
11. Price above the 200-day average
12. Beating the Nifty 50

A weekly BUY that is 12 weeks old or less is treated as **emerging**: it needs the
price above the 200-day average and a 3-month lead over the index. An older BUY is
**established** and must meet a stricter test: a rising 200-day average, within 15%
of the 52-week high, ahead of the index over both 6 and 12 months.

Size band: market cap between ₹1,000 Cr and ₹40,000 Cr.

Excluded up front: financial services, metals and mining, oil and gas, realty.
The checklist's ratios do not fit lenders, and commodity businesses look like
growth stocks at the top of a price cycle.

## What the report shows

| Tier | Meaning |
|---|---|
| **A, Actionable now** | Passes all 12 checks |
| **B, Watchlist** | Business passes gates 1 and 2, chart not ready. Shows exactly what the chart lacks |
| **C, Bench** (collapsed) | Proven business that is not inflecting right now |

Below the tiers: a funnel showing how many stocks pass each check, and a track
record of every earlier tier A pick against the index.

## Running it

```bash
pip install -r requirements.txt
python -m tests.test_offline     # 11 offline tests, about 5 seconds, no network
python main.py --sample          # 12 tickers, checks the live data path
python main.py                   # full run, about 400 pages, 10 to 12 minutes
```

## Checking the parser against the site

Every run prints how many pages yielded each field:

```
What the pages yielded (318 usable of 331):
  4 years of sales          318
  operating cash flow       314
  ROCE                      316
  ...
```

A line marked `LOW` means the parser no longer matches the site for that field.
`output/raw_pages.csv` holds exactly what was read from each page, so any company
can be compared with its screener.in page by eye. If screener.in refuses the
requests altogether, the run stops after 10 pages, says so in the report, and saves
the response it received to `output/debug_response.html`.

## GitHub Actions

`.github/workflows/screener.yml` runs every Saturday 06:00 UTC and on demand.
It commits `data/picks_log.csv` back to the repository and publishes `output/` to
GitHub Pages. It needs **Settings > Actions > General > Workflow permissions >
Read and write**, which the previous version already required.

## Tuning

Every threshold is in `config.py`. The funnel in the report shows which check
removes the most stocks.

- `PROMOTER_HOLDING_MIN = 0` admits professionally run companies with no promoter.
- `ROC_MIN` is 20 because ROCE is a pre-tax figure; it is the same bar as the 15%
  after-tax return used in the US screener.
- To screen a different list, save NSE symbols as `input/universe.csv`.

## Files

```
main.py                 entry point
config.py               every threshold
src/universe.py         NSE index lists, industry exclusions
src/fundamentals.py     screener.in fetch and parser, market-specific checks 6 and 7
src/checklist.py        the 12 checks, gates and tiers
src/chart.py            prices, 200-day average, relative strength, Supertrend
src/supertrend.py       the Supertrend indicator
src/tracklog.py         picks log and performance against the index
src/pipeline.py         ties the steps together, writes CSVs
src/report.py           HTML report
tests/                  offline tests with a fake screener.in page and fake Yahoo
data/                   picks_log.csv (tracked in git)
output/                 index.html, all_companies.csv, shortlist.csv, raw_pages.csv
```

Files from the old version that are no longer used and can be deleted:
`src/fetch.py`, `src/screen.py`, `src/score.py`, `src/technicals.py`, `diagnose.py`.

## Limits

- **Not validated.** No backtest stands behind these thresholds. The track record
  in the report is the evidence, and it needs months and dozens of picks to mean anything.
- **Pledge data is partial.** screener.in mentions a pledge only when it considers it
  material. No mention is treated as no pledge, which is not the same as zero.
- **screener.in has no official API.** Pages are read one at a time with a pause.
  A site redesign can break fields; the coverage table above is there to show it.
- **Governance is only partly captured.** Auditor changes, related-party dealings and
  management history need a manual check before acting on any name.
- **The picks log holds the screener's picks only.** It never contains your own
  trades or positions.

For research only. Not investment advice.
