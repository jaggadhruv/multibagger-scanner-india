"""
HTML report — India edition.

Same layout as US screener but:
  * Currency: ₹ instead of $
  * Market cap: "Cr" (crores) not "B" (billions)
  * Ticker link → screener.in (India's most popular research site)
  * Extra columns: Promoter %, Pledge % (India-specific signals)
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>India Multibagger Screener — {ts_short}</title>
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.7/css/jquery.dataTables.min.css">
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
<style>
  :root {{
    --bg: #fafbfc; --card: #ffffff; --border: #e1e4e8;
    --text: #24292e; --muted: #6a737d; --accent: #ff6b00;
    --good: #22863a; --warn: #b08800; --bad: #cb2431;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    margin: 0 auto; padding: 24px; max-width: 1900px;
  }}
  header {{ margin-bottom: 24px; }}
  h1 {{ margin: 0 0 4px; font-size: 24px; }}
  .flag {{ display: inline-block; padding: 2px 8px; background: #ff9933; color: #fff;
           border-radius: 3px; font-size: 12px; margin-right: 8px; vertical-align: middle; }}
  .meta {{ color: var(--muted); font-size: 13px; }}
  .cards {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px; margin: 20px 0;
  }}
  .card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 6px; padding: 12px 16px;
  }}
  .card .label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }}
  .card .value {{ font-size: 22px; font-weight: 600; margin-top: 4px; }}
  .criteria {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 6px; padding: 14px 18px; margin-bottom: 20px; font-size: 13px;
    line-height: 1.6;
  }}
  .criteria strong {{ color: var(--accent); }}
  table.dataTable {{
    background: var(--card); border: 1px solid var(--border); border-radius: 6px;
    font-size: 12.5px; width: 100% !important;
  }}
  table.dataTable thead th {{
    background: #f6f8fa; border-bottom: 2px solid var(--border);
    padding: 10px 8px; font-weight: 600; color: var(--text);
  }}
  table.dataTable tbody td {{ padding: 8px; border-bottom: 1px solid #eef1f4; vertical-align: top; }}
  table.dataTable tbody tr:hover {{ background: #f6f8fa; }}
  .rank {{ font-weight: 600; color: var(--muted); text-align: center; }}
  .ticker a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
  .ticker a:hover {{ text-decoration: underline; }}
  .rationale {{ font-size: 12px; color: #444; max-width: 340px; line-height: 1.4; }}
  .pos {{ color: var(--good); }}
  .neg {{ color: var(--bad); }}

  .score-badge {{
    display: inline-block; min-width: 40px; padding: 4px 8px;
    border-radius: 12px; font-weight: 700; font-size: 13px;
    text-align: center; color: white;
  }}
  .mb-elite    {{ background: #22863a; }}
  .mb-strong   {{ background: #2f9e5c; }}
  .mb-good     {{ background: #7cb342; color: #1a3d0a; }}
  .mb-fair     {{ background: #f0c040; color: #4a3800; }}
  .mb-marginal {{ background: #e0a040; color: #4a2800; }}
  .tech-great  {{ background: #22863a; }}
  .tech-good   {{ background: #7cb342; color: #1a3d0a; }}
  .tech-neutral{{ background: #f0c040; color: #4a3800; }}
  .tech-weak   {{ background: #e0a040; color: #4a2800; }}
  .tech-bad    {{ background: var(--bad); }}

  .signal {{
    display: inline-block; padding: 3px 10px; border-radius: 4px;
    font-weight: 700; font-size: 12px; letter-spacing: 0.5px;
  }}
  .signal-buy  {{ background: #d4edda; color: #155724; border: 1px solid #22863a; }}
  .signal-sell {{ background: #f8d7da; color: #721c24; border: 1px solid var(--bad); }}
  .signal-days {{ display: block; font-size: 10px; color: var(--muted); margin-top: 2px; font-weight: 400; }}

  .pledge-bad  {{ color: var(--bad); font-weight: 600; }}
  .pledge-warn {{ color: var(--warn); font-weight: 500; }}
  .pledge-ok   {{ color: var(--good); }}

  footer {{
    margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border);
    color: var(--muted); font-size: 12px;
  }}
  footer .disclaimer {{
    background: #fff8e1; border-left: 3px solid var(--warn);
    padding: 10px 14px; margin: 12px 0; color: #5c4a00;
  }}
</style>
</head>
<body>
<header>
  <h1><span class="flag">🇮🇳 India</span>Multibagger Candidate Screener</h1>
  <div class="meta">Generated {ts} · Fundamentals: screener.in · Prices: Yahoo Finance (.NS)</div>
</header>

<div class="cards">
  <div class="card"><div class="label">Universe scanned</div><div class="value">{universe:,}</div></div>
  <div class="card"><div class="label">Data fetched</div><div class="value">{fetched:,}</div></div>
  <div class="card"><div class="label">Passed filters</div><div class="value">{n_pass:,}</div></div>
  <div class="card"><div class="label">Shown in table</div><div class="value">{n_show:,}</div></div>
</div>

<div class="criteria">
<strong>Universe</strong>: Nifty Midcap 150 + Nifty Smallcap 250 (~400 tickers).<br>
<strong>Hard filters</strong>: Market cap ₹1,000–40,000 Cr · ROE ≥15% · ROCE ≥15% · OPM ≥10% · 5y sales/profit growth ≥10% · D/E ≤1.0 · Promoter holding ≥30% · Promoter pledge ≤10%.<br>
<strong>Multibagger Score (0-10, fundamental)</strong>: Quality (30%) + Health (25%) + Growth (20%) + <em>Promoter (15%)</em> + Valuation (10%). The Promoter factor is India-specific: high stable promoter holding + low pledge is the single best positive governance signal.<br>
<strong>Technical Score (0-10)</strong>: RSI 40-60 sweet spot + 5-20% above 200MA + 10-25% pullback from 52w high. Higher = better entry point.<br>
<strong>Supertrend (ATR period=10, mult=2.5)</strong>: <span class="signal signal-buy">BUY</span> = price above trend line; <span class="signal signal-sell">SELL</span> = price below.<br>
&nbsp;&nbsp;&nbsp;&nbsp;• <strong>ST Weekly</strong> — long-term trend (primary signal for multibagger holds)<br>
&nbsp;&nbsp;&nbsp;&nbsp;• <strong>ST Daily</strong> — short-term signal (entry-timing color)
</div>

{table}

<footer>
  <div class="disclaimer">
    <strong>Not investment advice.</strong> This screener is a candidate generator, not a buy list. Indian small caps in particular carry governance risks that no fundamental screen can fully capture — always cross-check auditor changes, related-party transactions, and management background before acting on any name. Data quality from screener.in is generally excellent but not guaranteed.
  </div>
  <div>Fundamentals: screener.in · Prices: Yahoo Finance · Universe: NSE Nifty indices</div>
</footer>

<script>
$(document).ready(function() {{
    $('#results').DataTable({{
        pageLength: 25,
        order: [[0, 'asc']],
        columnDefs: [
            {{ targets: 0, className: 'rank' }},
            {{ targets: -1, className: 'rationale' }},
        ]
    }});
}});
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ #
# Formatters (India-flavoured)
# ------------------------------------------------------------------ #

def _fmt_cr(x):
    """Market cap in Crores. e.g. 12345.6 → '₹12,346 Cr'"""
    if pd.isna(x): return "—"
    return f"₹{x:,.0f} Cr"


def _fmt_pct(x):
    """Screener values already in % form (15.0 means 15%)."""
    if pd.isna(x): return "—"
    cls = "pos" if x >= 0 else "neg"
    return f'<span class="{cls}">{x:.1f}%</span>'


def _fmt_pct_signed(x):
    """For signed values like distance from MA."""
    if pd.isna(x): return "—"
    cls = "pos" if x >= 0 else "neg"
    return f'<span class="{cls}">{x:+.1f}%</span>'


def _fmt_ratio(x):
    if pd.isna(x): return "—"
    return f"{x:.2f}"


def _fmt_rsi(x):
    if pd.isna(x): return "—"
    if 40 <= x <= 60:      cls = "pos"
    elif 30 <= x < 40 or 60 < x <= 70:  cls = ""
    else:                  cls = "neg"
    return f'<span class="{cls}">{x:.0f}</span>'


def _fmt_pledge(x):
    """Pledge %: 0 is great, <5 fine, 5-20 warn, >20 red flag."""
    if pd.isna(x): return "—"
    if x <= 0.5:   return f'<span class="pledge-ok">{x:.1f}%</span>'
    if x <= 10:    return f'<span class="pledge-warn">{x:.1f}%</span>'
    return f'<span class="pledge-bad">{x:.1f}%</span>'


def _screener_link(symbol):
    """Link to screener.in company page."""
    return f'<span class="ticker"><a href="https://www.screener.in/company/{symbol}/" target="_blank" rel="noopener">{symbol}</a></span>'


def _mb_badge(score):
    if pd.isna(score): return "—"
    if score >= 9.0:   cls = "mb-elite"
    elif score >= 8.0: cls = "mb-strong"
    elif score >= 7.0: cls = "mb-good"
    elif score >= 6.0: cls = "mb-fair"
    else:              cls = "mb-marginal"
    return f'<span class="score-badge {cls}" data-order="{score}">{score:.1f}</span>'


def _tech_badge(score):
    if pd.isna(score): return "—"
    if score >= 8.0:   cls = "tech-great"
    elif score >= 6.5: cls = "tech-good"
    elif score >= 5.0: cls = "tech-neutral"
    elif score >= 3.5: cls = "tech-weak"
    else:              cls = "tech-bad"
    return f'<span class="score-badge {cls}" data-order="{score}">{score:.1f}</span>'


def _supertrend_badge(signal, bars, unit="d"):
    if pd.isna(signal) or signal is None: return "—"
    cls = "signal-buy" if signal == "BUY" else "signal-sell"
    bars_str = f'<span class="signal-days">{int(bars)}{unit}</span>' if pd.notna(bars) else ""
    return f'<span class="signal {cls}" data-order="{signal}">{signal}</span>{bars_str}'


# ------------------------------------------------------------------ #
# Main entry
# ------------------------------------------------------------------ #

def generate_html_report(
    scored_df: pd.DataFrame,
    universe_size: int,
    fetched_size: int,
    output_path: str | Path,
    top_n: int = 50,
    diagnostics: dict | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    n_pass = len(scored_df)
    top = scored_df.head(top_n).copy()
    n_rows = len(top)

    # ------------- EMPTY STATE: show diagnostic message instead of table -------------
    if n_rows == 0:
        notes = (diagnostics or {}).get("notes", []) if diagnostics else []
        notes_html = ""
        if notes:
            items = "".join(f"<li>{n}</li>" for n in notes)
            notes_html = f"""
            <div class="empty-diag" style="background:#fff;border:1px solid #e1e4e8;border-radius:6px;padding:24px;margin:20px 0;">
                <h2 style="margin-top:0;color:#cb2431;">⚠️ No candidates to display</h2>
                <p><strong>What happened:</strong></p>
                <ul>{items}</ul>
                <p><strong>Next steps to diagnose:</strong></p>
                <ol>
                  <li>Download this run's artifact from the GitHub Actions run — contains <code>raw_data.csv</code> with per-ticker <code>error</code> column showing exactly why each fetch failed.</li>
                  <li>Look for <code>debug_response.html</code> in the artifact — the first blocked response is saved there. If it's a Cloudflare/bot challenge page, screener.in is blocking the GitHub Actions runner IP.</li>
                  <li>If IP blocking is confirmed: run <code>python main.py</code> locally (from a residential IP), commit the resulting <code>output/scored.csv</code>, then have Actions run with <code>--skip-fundamentals</code> to just do technicals + report.</li>
                  <li>If parsers came up empty but got valid HTML: screener.in may have changed page structure — update the CSS selectors in <code>src/fetch.py</code>.</li>
                </ol>
            </div>
            """
        table_html = notes_html or '<div class="empty-diag" style="padding:24px;text-align:center;color:#6a737d;"><h2>No data available for this run.</h2><p>Check GitHub Actions logs for details.</p></div>'
    else:
        # ------------- NORMAL PATH: build the table -------------
        _none = pd.Series([None] * n_rows, index=top.index)

        def _col(name):
            return top.get(name, _none)

        display = pd.DataFrame({
            "Rank":         range(1, n_rows + 1),
            "Symbol":       top["symbol"].apply(_screener_link),
            "Name":         _col("name").fillna("").astype(str).str.slice(0, 30),
            "Mkt Cap":      top["market_cap_cr"].apply(_fmt_cr),
            "MB /10":       top["multibagger_score"].apply(_mb_badge),
            "Tech /10":     _col("technical_score").apply(_tech_badge),
            "ST Weekly":    [_supertrend_badge(s, w, "w") for s, w in
                             zip(_col("supertrend_weekly_signal"), _col("supertrend_weekly_weeks"))],
            "ST Daily":     [_supertrend_badge(s, d, "d") for s, d in
                             zip(_col("supertrend_daily_signal"), _col("supertrend_daily_days"))],
            "Promoter":     _col("promoter_holding").apply(_fmt_pct),
            "Pledge":       _col("promoter_pledge").apply(_fmt_pledge),
            "ROE":          _col("roe").apply(_fmt_pct),
            "ROCE":         _col("roce").apply(_fmt_pct),
            "5y Sales":     _col("sales_growth_5y").apply(_fmt_pct),
            "5y Profit":    _col("profit_growth_5y").apply(_fmt_pct),
            "D/E":          _col("debt_to_equity").apply(_fmt_ratio),
            "P/E":          _col("pe_ratio").apply(_fmt_ratio),
            "RSI":          _col("rsi_14").apply(_fmt_rsi),
            "vs 200MA":     _col("pct_from_200ma").apply(_fmt_pct_signed),
            "Rationale":    _col("rationale").fillna("—"),
        })

        table_html = display.to_html(
            table_id="results",
            classes="display compact",
            index=False,
            escape=False,
            border=0,
        )

    now = datetime.now(timezone.utc)
    html = HTML_TEMPLATE.format(
        ts=now.strftime("%Y-%m-%d %H:%M UTC"),
        ts_short=now.strftime("%Y-%m-%d"),
        universe=universe_size,
        fetched=fetched_size,
        n_pass=n_pass,
        n_show=n_rows,
        table=table_html,
    )

    output_path.write_text(html, encoding="utf-8")
    print(f"Report written: {output_path.resolve()}")
    return output_path
