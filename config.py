"""
Every setting for the India screener lives here. Change a number, run again.

Percentages are plain numbers: 15.0 means 15%. Money is in Rs crore.
"""

# ------------------------------------------------------------------ #
# Market
# ------------------------------------------------------------------ #
MARKET = "IN"
REPORT_TITLE = "India Multibagger Shortlist"
UNIVERSE_NAME = "Nifty Midcap 150 + Smallcap 250"
FUNDAMENTALS_SOURCE = "screener.in"
CURRENCY = "₹"
CAP_UNIT = "crore"
TICKER_URL = "https://www.screener.in/company/{ticker}/"
PRICE_SUFFIX = ".NS"                    # NSE tickers on Yahoo Finance
BENCHMARK_SYMBOLS = ["^NSEI", "NIFTYBEES.NS"]   # tried in order
BENCHMARK_NAME = "Nifty 50"

# ------------------------------------------------------------------ #
# Universe
# ------------------------------------------------------------------ #
# NSE industry groups where the checklist does not work. Lenders and insurers
# have no meaningful operating margin or debt ratio. Metals, oil and gas look
# like growth stocks at the top of a price cycle. Realty books revenue when
# projects complete, so year-by-year revenue checks mean little.
EXCLUDED_INDUSTRIES = [
    "Financial Services", "Metals & Mining", "Oil Gas & Consumable Fuels", "Realty", "Forest Materials",
]
# Second net, applied to the sector line on each screener.in page
EXCLUDED_INDUSTRY_KEYWORDS = [
    "financial services", "bank", "finance", "nbfc", "insurance", "broking", "asset management", "steel", "aluminium", "mining",
    "metals", "refineries", "oil exploration", "coal", "sugar", "paper", "fertiliz", "shipping", "realty",
]

# Size band in Rs crore
MARKET_CAP_MIN = 1_000
MARKET_CAP_MAX = 40_000

# ------------------------------------------------------------------ #
# Gate 1: proven business
# ------------------------------------------------------------------ #
REV_CAGR_MIN = 15.0                 # sales growth, % a year over 3 years
ROC_LABEL = "Return on capital employed"
ROC_SHORT = "ROCE"
ROC_MIN = 20.0                      # ROCE is before tax, so 20% here is the same bar as 15% after tax
CASH_LABEL = "Operating cash flow"
CASH_POSITIVE_YEARS_MIN = 3         # of the last 4 years
CASH_CONVERSION_MIN = 70.0          # 3-year operating cash flow as % of 3-year net profit
DEBT_TO_EQUITY_MAX = 0.6            # borrowings / (equity capital + reserves)
PROMOTER_HOLDING_MIN = 30.0         # %. Set to 0 to allow professionally run companies with no promoter
PROMOTER_DROP_MAX_PP = 3.0          # promoters must not have sold more than this over about a year
PROMOTER_PLEDGE_MAX = 5.0           # % of promoter holding pledged, when screener.in reports a pledge

# ------------------------------------------------------------------ #
# Gate 2: early / inflecting
# ------------------------------------------------------------------ #
MARGIN_EXPANSION_MIN_PP = 1.0       # operating margin now vs 3 years ago, percentage points
MARGIN_RECENT_DIP_MAX_PP = 1.5      # ...and not down more than this against last year
GROWTH_NOW_MIN = 12.0               # latest fiscal year sales growth, %
GROWTH_FADE_RATIO = 0.6             # latest growth must be at least this share of the 3-year pace
RECENT_QUARTER_GROWTH_MIN = 8.0     # latest quarter vs a year ago, %

# ------------------------------------------------------------------ #
# Gate 3: chart strength
# ------------------------------------------------------------------ #
FRESH_FLIP_WEEKS = 12               # weekly Supertrend BUY this young counts as "emerging"
NEAR_HIGH_MAX_PCT = 15.0            # established trends must be within this % of the 52-week high
EXTENDED_ABOVE_200_PCT = 40.0       # caution flag only, never changes the tier
RSI_HOT = 75.0                      # caution flag only

# ------------------------------------------------------------------ #
# Data fetching
# ------------------------------------------------------------------ #
FETCH_DELAY = 0.4                   # seconds between Yahoo price calls
SCREENER_DELAY = 0.8                # seconds between screener.in pages

# Text shown in the report's Method section for the two market-specific checks
METHOD_ITEM_6 = f"Borrowings of no more than {DEBT_TO_EQUITY_MAX:g} times shareholders' funds"
METHOD_ITEM_7 = (f"Promoters hold at least {PROMOTER_HOLDING_MIN:g}%, have not sold more than {PROMOTER_DROP_MAX_PP:g} "
                 f"points over a year, and no pledge above {PROMOTER_PLEDGE_MAX:g}% is flagged on screener.in")
