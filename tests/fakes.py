"""
Stand-ins for screener.in and Yahoo Finance so the pipeline can be tested
with no network.

make_page() writes HTML with the same structure and row labels as a real
screener.in company page: label cells with a trailing "+" button, a TTM
column, a half-year balance-sheet column, two shareholding tables and the
small compounded-growth tables in between.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

END = pd.Timestamp("2026-11-13")  # a Friday

YEARS = [f"Mar {y}" for y in range(2015, 2027)]                                   # 12 fiscal years
QUARTERS = ["Sep 2023", "Dec 2023", "Mar 2024", "Jun 2024", "Sep 2024", "Dec 2024", "Mar 2025",
            "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"]
HOLD_Q = QUARTERS[1:]
HOLD_Y = [f"Mar {y}" for y in range(2017, 2027)] + ["Sep 2026"]

# Figures read from the live Astral page on 2026-11-15 (rows not shown there are filled in)
ASTRAL = dict(
    name="Astral Ltd", market_cap="33,689", price="1,254", pe="56.9", roce_now="19.2", roe_now="13.9",
    sales=[1410, 1678, 1895, 2073, 2507, 2578, 3176, 4394, 5158, 5641, 5832, 6569], sales_ttm=7196,
    expenses=[1242, 1470, 1633, 1759, 2126, 2136, 2539, 3640, 4349, 4717, 4886, 5507], expenses_ttm=6084,
    net_profit=[76, 101, 145, 176, 197, 250, 408, 490, 472, 546, 524, 590], net_profit_ttm=640,
    q_sales=[1363, 1370, 1625, 1384, 1370, 1397, 1681, 1361, 1577, 1542, 2088, 1578, 1988],
    equity_capital=[12, 12, 12, 12, 12, 15, 20, 20, 27, 27, 27, 27, 27],
    reserves=[607, 696, 835, 1006, 1266, 1488, 1876, 2316, 2684, 3161, 3590, 4031, 4212],
    borrowings=[150, 160, 170, 180, 190, 150, 60, 80, 90, 110, 120, 130, 120],
    cfo=[117, 226, 114, 282, 342, 405, 664, 543, 557, 823, 630, 1117],
    fcf=[32, 91, -45, 98, 122, 192, 493, 198, 247, 273, 90, 661],
    roce=[24, 23, 24, 23, 22, 21, 27, 27, 23, 22, 20, 19],
    promoters_q=[54.10] * 7 + [54.21] + [54.22] * 4,
    promoters_y=[59.34, 58.50, 58.48, 55.74, 55.74, 55.73, 55.85, 54.10, 54.10, 54.22, 54.22],
    pros=["Company is almost debt free."], cons=["Stock is trading at 7.95 times its book value"],
    breadcrumb=["Industrials", "Capital Goods", "Industrial Products", "Plastic Products - Industrial"],
)


def _n(v) -> str:
    if v is None:
        return ""
    return f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) and v != int(v) else f"{int(v):,}"


def _table(headers, rows, expandable=()) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for i, (label, values, suffix) in enumerate(rows):
        if label in expandable:
            cell = (f'<button class="button-plain" onclick="Company.showSchedule(\'{label}\', this)">'
                    f'{label}&nbsp;<span class="blue-icon">+</span></button>')
        else:
            cell = label
        tds = "".join(f"<td>{_n(v)}{suffix if v is not None else ''}</td>" for v in values)
        body += f'<tr class="{"stripe" if i % 2 == 0 else ""}"><td class="text">{cell}</td>{tds}</tr>\n'
    return ('<div class="responsive-holder fill-card-width"><table class="data-table responsive-text-nowrap">'
            f'<thead><tr><th class="text"></th>{head}</tr></thead><tbody>\n{body}</tbody></table></div>')


def _ranges(title, pairs) -> str:
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in pairs)
    return f'<table class="ranges-table"><tr><th colspan="2">{title}</th></tr>{rows}</table>'


def make_page(name="Test Ltd", market_cap="5,000", price="500", pe="40", roce_now="25", roe_now="20",
              sales=None, sales_ttm=None, expenses=None, expenses_ttm=None, net_profit=None, net_profit_ttm=None,
              q_sales=None, equity_capital=None, reserves=None, borrowings=None, cfo=None, fcf=None, roce=None,
              promoters_q=None, promoters_y=None, pros=(), cons=(), breadcrumb=(), financial=False) -> str:
    sales = list(sales)
    expenses = list(expenses)
    op = [s - e for s, e in zip(sales, expenses)]
    opm = [round(o / s * 100) for o, s in zip(op, sales)]
    s_ttm, e_ttm = sales_ttm or sales[-1], expenses_ttm or expenses[-1]
    np_ttm = net_profit_ttm or net_profit[-1]
    q_sales = list(q_sales)
    q_exp = [round(q * 0.84) for q in q_sales]
    sales_label, op_label, opm_label = ("Revenue", "Financing Profit", "Financing Margin %") if financial else ("Sales", "Operating Profit", "OPM %")

    pl_rows = [
        (sales_label, sales + [s_ttm], ""), ("Interest" if financial else "Expenses", expenses + [e_ttm], ""),
        (op_label, op + [s_ttm - e_ttm], ""), (opm_label, opm + [round((s_ttm - e_ttm) / s_ttm * 100)], "%"),
        ("Other Income", [5] * 13, ""), ("Depreciation", [20] * 13, ""),
        ("Profit before tax", [round(x * 1.33) for x in net_profit] + [round(np_ttm * 1.33)], ""),
        ("Tax %", [25] * 13, "%"), ("Net Profit", list(net_profit) + [np_ttm], ""),
        ("EPS in Rs", [round(x / 27, 2) for x in net_profit] + [round(np_ttm / 27, 2)], ""),
        ("Dividend Payout %", [15] * 12 + [None], "%"),
    ]
    q_rows = [
        (sales_label, q_sales, ""), ("Expenses", q_exp, ""), (op_label, [a - b for a, b in zip(q_sales, q_exp)], ""),
        (opm_label, [16] * 13, "%"), ("Other Income", [3] * 13, ""), ("Interest", [8] * 13, ""),
        ("Depreciation", [50] * 13, ""), ("Profit before tax", [round(q * 0.11) for q in q_sales], ""),
        ("Tax %", [25] * 13, "%"), ("Net Profit", [round(q * 0.08) for q in q_sales], ""),
        ("EPS in Rs", [round(q * 0.003, 2) for q in q_sales], ""), ("Raw PDF", [None] * 13, ""),
    ]
    total = [c + r + b + 500 for c, r, b in zip(equity_capital, reserves, borrowings)]
    bs_rows = [
        ("Equity Capital", equity_capital, ""), ("Reserves", reserves, ""), ("Borrowings", borrowings, ""),
        ("Other Liabilities", [500] * 13, ""), ("Total Liabilities", total, ""), ("Fixed Assets", [t * 0.5 for t in total], ""),
        ("CWIP", [40] * 13, ""), ("Investments", [10] * 13, ""), ("Other Assets", [t * 0.4 for t in total], ""),
        ("Total Assets", total, ""),
    ]
    cf_rows = [
        ("Cash from Operating Activity", cfo, ""), ("Cash from Investing Activity", [-abs(c) * 0.6 for c in cfo], ""),
        ("Cash from Financing Activity", [-abs(c) * 0.3 for c in cfo], ""), ("Net Cash Flow", [c * 0.1 for c in cfo], ""),
        ("Free Cash Flow", fcf, ""), ("CFO/EBITDA", [90] * 12, "%"),
    ]
    ratio_rows = [
        ("Debtor Days", [30] * 12, ""), ("Inventory Days", [100] * 12, ""), ("Days Payable", [70] * 12, ""),
        ("Cash Conversion Cycle", [60] * 12, ""), ("Working Capital Days", [20] * 12, ""), ("ROCE %", roce, "%"),
    ]

    def hold_rows(promoters):
        n = len(promoters)
        if all(p is None for p in promoters):
            return [("FIIs", [40.0] * n, "%"), ("DIIs", [35.0] * n, "%"), ("Public", [25.0] * n, "%"),
                    ("No. of Shareholders", [100000] * n, "")]
        return [("Promoters", promoters, "%"), ("FIIs", [15.5] * n, "%"), ("DIIs", [20.25] * n, "%"),
                ("Government", [0.0] * n, "%"), ("Public", [10.0] * n, "%"), ("No. of Shareholders", [250000] * n, "")]

    ratios = [("Market Cap", f'₹ <span class="number">{market_cap}</span> Cr.'),
              ("Current Price", f'₹ <span class="number">{price}</span>'),
              ("High / Low", '₹ <span class="number">1,769</span> / <span class="number">1,216</span>'),
              ("Stock P/E", f'<span class="number">{pe}</span>'), ("Book Value", '₹ <span class="number">158</span>'),
              ("Dividend Yield", '<span class="number">0.32</span> %'), ("ROCE", f'<span class="number">{roce_now}</span> %'),
              ("ROE", f'<span class="number">{roe_now}</span> %'), ("Face Value", '₹ <span class="number">1.00</span>')]
    top = "".join(f'<li class="flex flex-space-between" data-source="default"><span class="name">\n{k}\n</span>'
                  f'<span class="nowrap value">{v}</span></li>' for k, v in ratios)
    crumbs = " ".join(f'<a href="/market/IN0{i}/" target="_blank">{b}</a>' for i, b in enumerate(breadcrumb))
    expand = ("Sales", "Revenue", "Expenses", "Other Income", "Net Profit", "Borrowings", "Other Liabilities",
              "Fixed Assets", "Other Assets", "Cash from Operating Activity", "Cash from Investing Activity",
              "Cash from Financing Activity", "Promoters", "FIIs", "DIIs", "Government", "Public")
    return f"""<!DOCTYPE html><html><head><title>{name} share price | Screener</title></head><body>
<nav><ul><li><a href="/">Home</a></li><li><a href="/screens/">Screens</a></li></ul></nav>
<div id="top"><h1 class="margin-0 show-from-tablet-landscape">{name}</h1>
<div class="company-ratios"><ul id="top-ratios">{top}</ul></div></div>
<section id="analysis"><div class="flex"><div class="pros"><p class="title">Pros</p><ul>{"".join(f"<li>{p}</li>" for p in pros)}</ul></div>
<div class="cons"><p class="title">Cons</p><ul>{"".join(f"<li>{c}</li>" for c in cons)}</ul></div></div></section>
<section id="peers"><h2>Peer comparison</h2><p class="sub">{crumbs}</p><div id="peers-table-placeholder">Loading peers table ...</div></section>
<section id="quarters"><h2>Quarterly Results</h2>{_table(QUARTERS, q_rows, expand)}</section>
<section id="profit-loss"><h2>Profit &amp; Loss</h2>{_table(YEARS + ["TTM"], pl_rows, expand)}
{_ranges("Compounded Sales Growth", [("10 Years:", "15%"), ("5 Years:", "16%"), ("3 Years:", "8%"), ("TTM:", "20%")])}
{_ranges("Compounded Profit Growth", [("10 Years:", "18%"), ("5 Years:", "6%"), ("3 Years:", "6%"), ("TTM:", "16%")])}
{_ranges("Stock Price CAGR", [("10 Years:", "21%"), ("5 Years:", "-6%"), ("3 Years:", "-13%"), ("1 Year:", "-17%")])}
{_ranges("Return on Equity", [("10 Years:", "18%"), ("5 Years:", "17%"), ("3 Years:", "15%"), ("Last Year:", "14%")])}</section>
<section id="balance-sheet"><h2>Balance Sheet</h2>{_table(YEARS + ["Sep 2026"], bs_rows, expand)}</section>
<section id="cash-flow"><h2>Cash Flows</h2>{_table(YEARS, cf_rows, expand)}</section>
<section id="ratios"><h2>Ratios</h2>{_table(YEARS, ratio_rows, expand)}</section>
<section id="shareholding"><h2>Shareholding Pattern</h2>
<div id="quarterly-shp">{_table(HOLD_Q, hold_rows(promoters_q), expand)}</div>
<div id="yearly-shp" class="hidden">{_table(HOLD_Y, hold_rows(promoters_y), expand)}</div></section>
</body></html>"""


def strong_page(name: str, **changes) -> str:
    """A company that passes gates 1 and 2: 25% growth, expanding margins, high ROCE, cash-backed."""
    sales = [round(300 * 1.25 ** i) for i in range(12)]
    margins = [0.14] * 8 + [0.15, 0.165, 0.18, 0.195]
    expenses = [round(s * (1 - m)) for s, m in zip(sales, margins)]
    net = [round((s - e) * 0.7) for s, e in zip(sales, expenses)]
    last = sales[-1] / 4
    spec = dict(
        name=name, market_cap="12,500", pe="45", sales=sales, expenses=expenses, net_profit=net,
        q_sales=[round(last * (0.72 + 0.045 * i)) for i in range(13)],
        equity_capital=[20] * 13, reserves=[round(200 * 1.22 ** i) for i in range(13)], borrowings=[40] * 13,
        cfo=[round(x * 0.95) for x in net], fcf=[round(x * 0.5) for x in net], roce=[24] * 8 + [26, 28, 30, 32],
        promoters_q=[61.5] * 12, promoters_y=[62.0] * 11, cons=[], pros=["Company has delivered good profit growth"],
        breadcrumb=["Industrials", "Capital Goods", "Electrical Equipment", "Other Electrical Equipment"],
    )
    spec.update(changes)
    return make_page(**spec)


def price_path(kind: str, seed: int = 1, bars: int = 756, start: float = 400.0) -> pd.DataFrame:
    """Daily OHLC for a named shape: 'established', 'emerging', 'downtrend' or 'index'."""
    rng = np.random.default_rng(seed)
    if kind == "established":
        drift = np.full(bars, 0.0016)
    elif kind == "emerging":      # flat, then a year-long slide, then a sharp 8-week recovery
        drift = np.concatenate([np.zeros(bars - 256), np.full(216, -0.002), np.full(40, 0.011)])
    elif kind == "downtrend":
        drift = np.full(bars, -0.0012)
    elif kind == "index":
        drift = np.full(bars, 0.0004)
    else:
        raise ValueError(kind)
    close = start * np.exp(np.cumsum(drift + rng.normal(0, 0.004, bars)))
    idx = pd.bdate_range(end=END, periods=bars, tz="Asia/Kolkata")
    spread = close * 0.008
    return pd.DataFrame({
        "Open": close - spread / 4, "High": close + spread, "Low": close - spread, "Close": close,
        "Volume": rng.integers(200_000, 900_000, bars), "Dividends": 0.0, "Stock Splits": 0.0,
    }, index=idx)


class FakeYahoo:
    """Price history only. Use as: patch('yfinance.Ticker', fake.Ticker)."""

    def __init__(self, prices=None):
        self.prices = prices or {}
        self.calls: list[str] = []

    def Ticker(self, symbol):  # noqa: N802 - mirrors yfinance
        world = self

        class _T:
            def history(self, **_):
                world.calls.append(symbol)
                return world.prices.get(symbol, pd.DataFrame())
        return _T()
