"""Aggregates every ticker currently in reports/ into one dashboard page:
reports/summary_report.html — a table with links to each ticker's full
report, plus two interactive charts (X-Y scatter and time-trend) driven by
quarterly_timeseries data from each ticker's data/{TICKER}_quant.json.
Reads only what's already on disk; never runs the pipeline itself (that
stays a deliberate, manual — or Claude-Code-orchestrated — step, since the
interpretive agents can't run headlessly without reintroducing API
billing).

The two charts need actual interactivity (axis/ticker dropdowns that
re-plot without a server round-trip), which isn't possible in pure static
SVG — this page embeds a small amount of inline vanilla JS to do that. No
external CDN, no framework, no build step; still a single self-contained
file, just no longer a *script-free* one like render_html.py's reports.

    python summary_report.py                 # build reports/summary_report.html
    python summary_report.py --check-stale    # just list tickers not run in 30+ days
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from quant import archive

DATA_DIR = Path(__file__).parent / "data"
REPORTS_DIR = Path(__file__).parent / "reports"

# Kept in sync with quant_agent.py's quarterly_timeseries.metric_labels —
# duplicated here (rather than read from one ticker's file) since every
# ticker's quant.json defines the same fixed set of metrics.
METRIC_LABELS = {
    "fcf_ttm": "FCF (TTM)",
    "roe_ttm": "ROE (TTM)",
    "pe_ttm": "P/E (TTM)",
}

CSS = """
:root {
  color-scheme: light dark;
  --bg: #ffffff;
  --fg: #1a1a1a;
  --muted: #5b6470;
  --border: #e2e5e9;
  --card-bg: #f7f8fa;
  --accent: #2f6fed;
  --stale-bg: #fff7e6;
  --stale-border: #f0b429;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14161a;
    --fg: #e8eaed;
    --muted: #9aa4b2;
    --border: #2b2f36;
    --card-bg: #1c1f25;
    --accent: #6fa0ff;
    --stale-bg: #2a2210;
    --stale-border: #a67c00;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Pretendard, "Apple SD Gothic Neo",
               "Noto Sans KR", sans-serif;
  line-height: 1.6;
}
.page { max-width: 920px; margin: 0 auto; padding: 48px 24px 80px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
.subtitle { color: var(--muted); font-size: 0.92rem; margin: 0 0 32px; }
h2 { font-size: 1.2rem; margin: 40px 0 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.muted { color: var(--muted); }

.table-scroll { overflow-x: auto; }
table.summary-table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 0.92rem; }
.summary-table th, .summary-table td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
.summary-table th { color: var(--muted); font-weight: 600; background: var(--card-bg); }
.summary-table a { color: var(--accent); text-decoration: none; }
.summary-table a:hover { text-decoration: underline; }
.summary-table td.moat-cell { max-width: 320px; white-space: normal; font-size: 0.87rem; color: var(--muted); }

.stale-badge {
  display: inline-block;
  background: var(--stale-bg);
  border: 1px solid var(--stale-border);
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 0.85rem;
}

.chart-wrap { max-width: 760px; }
.interactive-chart { width: 100%; height: auto; }
.chart-grid { stroke: var(--border); stroke-width: 1; }
.chart-tick { fill: var(--muted); font-size: 11px; }
.chart-axis-title { fill: var(--muted); font-size: 12px; }
.chart-label { font-size: 11px; font-weight: 600; }
.chart-empty-note { color: var(--muted); font-size: 0.9rem; padding: 16px 0; }

.chart-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  align-items: flex-start;
  margin-bottom: 16px;
  padding: 14px 16px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.chart-controls .control-group { display: flex; flex-direction: column; gap: 4px; }
.chart-controls label.control-title { font-size: 0.78rem; color: var(--muted); font-weight: 600; }
.chart-controls select {
  font-size: 0.88rem;
  padding: 5px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--fg);
}
.ticker-checkboxes { display: flex; flex-wrap: wrap; gap: 4px 12px; max-width: 420px; }
.ticker-checkboxes label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.85rem;
  cursor: pointer;
}
.ticker-checkboxes input { cursor: pointer; }
"""

PAGE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>밸류에이션 갭 요약 대시보드</title>
<style>
{css}
</style>
</head>
<body>
<div class="page">
<h1>밸류에이션 갭 요약 대시보드</h1>
<p class="subtitle">{generated_at} 기준 · {ticker_count}개 티커 · 각 항목 클릭 시 개별 리포트로 이동</p>
<h2>티커별 요약</h2>
{table}

<h2>분기별 지표 산점도 (X-Y)</h2>
<p class="muted" style="font-size:0.85rem; margin-top:-8px;">
각 티커가 보유한 모든 분기의 (X, Y) 값을 점으로 표시하고, 시간 순서대로 얇은 선으로 연결합니다.
가장 최근 분기는 큰 점으로 강조됩니다. 점에 마우스를 올리면 정확한 값을 볼 수 있습니다.
</p>
<div class="chart-controls" id="scatter-controls">
  <div class="control-group">
    <label class="control-title" for="scatter-x">X축 지표</label>
    <select id="scatter-x">{scatter_x_options}</select>
  </div>
  <div class="control-group">
    <label class="control-title" for="scatter-y">Y축 지표</label>
    <select id="scatter-y">{scatter_y_options}</select>
  </div>
  <div class="control-group">
    <label class="control-title">티커</label>
    <div class="ticker-checkboxes">{scatter_ticker_checkboxes}</div>
  </div>
</div>
<div class="chart-wrap">
<svg id="scatter-svg" class="interactive-chart" role="img" aria-label="분기별 지표 산점도"></svg>
<p class="chart-empty-note" id="scatter-empty-note" style="display:none;">
선택된 티커·지표 조합에 데이터가 없습니다.
</p>
</div>

<h2>분기별 지표 시계열 추세</h2>
<p class="muted" style="font-size:0.85rem; margin-top:-8px;">
X축은 분기, Y축은 선택한 지표입니다. 각 티커가 보유한 모든 분기 데이터를 선으로 이어 표시합니다.
</p>
<div class="chart-controls" id="trend-controls">
  <div class="control-group">
    <label class="control-title" for="trend-y">Y축 지표</label>
    <select id="trend-y">{trend_y_options}</select>
  </div>
  <div class="control-group">
    <label class="control-title">티커</label>
    <div class="ticker-checkboxes">{trend_ticker_checkboxes}</div>
  </div>
</div>
<div class="chart-wrap">
<svg id="trend-svg" class="interactive-chart" role="img" aria-label="분기별 지표 시계열 추세"></svg>
<p class="chart-empty-note" id="trend-empty-note" style="display:none;">
선택된 티커·지표 조합에 데이터가 없습니다.
</p>
</div>

<p class="muted" style="margin-top:32px; font-size:0.85rem;">
⚠️ 본 페이지는 정보 제공 목적의 정량적 밸류에이션 요약이며, 투자 자문이나 매수/매도 추천이 아닙니다.
분기 지표(FCF/ROE/P·E)는 모두 트레일링 12개월(TTM) 기준이며, P/E는 각 분기 시점의 실제 발행주식수가
아니라 현재 발행주식수로 근사한 값이라 자사주매입·증자가 많았던 종목은 과거 구간의 정확도가 떨어질 수
있습니다.
</p>
</div>
<script>
{chart_js}
</script>
</body>
</html>
"""


def _load_ticker_summary(ticker: str) -> dict:
    ticker = ticker.upper()
    quant_path = DATA_DIR / f"{ticker}_quant.json"
    moat_path = DATA_DIR / f"{ticker}_tech_moat.json"

    current_price = fair_value = gap_pct = trailing_pe = roe = as_of = None
    if quant_path.exists():
        quant = json.loads(quant_path.read_text())
        dcf_out = quant.get("dcf_model_output", {})
        rel = quant.get("relative_valuation", {})
        current_price = dcf_out.get("current_price")
        fair_value = dcf_out.get("fair_value_per_share")
        gap_pct = dcf_out.get("valuation_gap_pct")
        trailing_pe = rel.get("comps_multiples", {}).get("trailing_pe")
        roe = rel.get("profitability", {}).get("return_on_equity")
        as_of = quant.get("as_of")

    primary_moat = None
    if moat_path.exists():
        moat = json.loads(moat_path.read_text())
        primary_moat = moat.get("moat_evaluation", {}).get("primary_moat_type")

    last_run = archive.get_last_run_date(ticker)

    return {
        "ticker": ticker,
        "current_price": current_price,
        "fair_value_per_share": fair_value,
        "valuation_gap_pct": gap_pct,
        "trailing_pe": trailing_pe,
        "roe": roe,
        "primary_moat": primary_moat,
        "as_of": as_of,
        "last_run_date": last_run.isoformat() if last_run else None,
    }


def _shorten(text: str, max_len: int = 90) -> str:
    """Trim a long moat description to a scannable snippet for the summary
    table — the full text is still in the ticker's own report, this is just
    a preview so the dashboard row stays readable."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut + "…"


def _build_table_html(rows: list[dict]) -> str:
    lines = [
        '<div class="table-scroll">',
        '<table class="summary-table">',
        "<thead><tr><th>티커</th><th>현재가</th><th>DCF 적정가</th>"
        "<th>괴리율</th><th>핵심 해자</th><th>최근 실행일</th><th></th></tr></thead>",
        "<tbody>",
    ]
    for r in rows:
        gap = r["valuation_gap_pct"]
        gap_str = f"{gap * 100:+.1f}%" if gap is not None else "insufficient_data"
        price_str = f"${r['current_price']:.2f}" if r["current_price"] is not None else "—"
        fv_str = f"${r['fair_value_per_share']:.2f}" if r["fair_value_per_share"] is not None else "—"
        moat_str = _shorten(r["primary_moat"]) if r["primary_moat"] else "—"
        if r["is_stale"]:
            run_cell = f'<span class="stale-badge">⚠ {r["last_run_date"] or "실행 이력 없음"}</span>'
        else:
            run_cell = r["last_run_date"] or "—"
        lines.append(
            f'<tr><td><a href="{r["ticker"]}_report.html">{r["ticker"]}</a></td>'
            f"<td>{price_str}</td><td>{fv_str}</td><td>{gap_str}</td>"
            f'<td class="moat-cell">{moat_str}</td><td>{run_cell}</td>'
            f'<td><a href="{r["ticker"]}_report.html">리포트 보기 →</a></td></tr>'
        )
    lines.append("</tbody></table>")
    lines.append("</div>")
    return "\n".join(lines)


def _collect_quarterly_timeseries(tickers: list[str]) -> dict[str, dict[str, dict[str, float]]]:
    """{ticker: {quarter_label: {metric_key: value}}} for every ticker that
    has a data/{TICKER}_quant.json with a quarterly_timeseries section.
    Tickers with none (e.g. SPCX — no SEC 10-K/10-Q history) are simply
    absent, not fabricated as empty series."""
    result: dict[str, dict[str, dict[str, float]]] = {}
    for ticker in tickers:
        quant_path = DATA_DIR / f"{ticker}_quant.json"
        if not quant_path.exists():
            continue
        quant = json.loads(quant_path.read_text())
        metrics = quant.get("quarterly_timeseries", {}).get("metrics")
        if metrics:
            result[ticker] = metrics
    return result


def _build_metric_options(default: str) -> str:
    options = []
    for key, label in METRIC_LABELS.items():
        selected = " selected" if key == default else ""
        options.append(f'<option value="{key}"{selected}>{label}</option>')
    return "".join(options)


def _build_ticker_checkboxes(tickers: list[str], name: str) -> str:
    boxes = []
    for ticker in tickers:
        boxes.append(
            f'<label><input type="checkbox" name="{name}" value="{ticker}" checked> {ticker}</label>'
        )
    return "".join(boxes)


def _build_chart_js(chart_data: dict, tickers: list[str]) -> str:
    """Inline vanilla JS (no CDN, no framework) that renders both
    interactive charts into their <svg> containers and re-renders on any
    dropdown/checkbox change. See render_scatter/render_trend for the SVG
    generation logic, mirrored from the project's earlier hand-rolled
    Python SVG chart (same axis-scaling approach, just executed
    client-side so it can respond to control changes)."""
    return f"""
const CHART_DATA = {json.dumps(chart_data)};
const METRIC_LABELS = {json.dumps(METRIC_LABELS)};
const TICKERS = {json.dumps(tickers)};
const COLORS = ["#2f6fed","#e0663d","#2ea043","#c9366f","#9457eb","#c9a227","#12a594","#e85d75","#5c6bc0","#8d6e63"];

function colorFor(ticker) {{
  return COLORS[TICKERS.indexOf(ticker) % COLORS.length];
}}

function niceRange(values) {{
  const min = Math.min.apply(null, values);
  const max = Math.max.apply(null, values);
  const pad = (max - min) * 0.12 || Math.abs(max || 1) * 0.12 || 1;
  let lo = min - pad;
  const hi = max + pad;
  // Padding shouldn't manufacture a negative axis floor when every actual
  // value is non-negative (e.g. an outlier P/E just needs a wide axis, not
  // a fake negative gridline) — metrics that can genuinely go negative
  // (ROE, FCF) are unaffected since min < 0 skips this clamp.
  if (min >= 0) lo = Math.max(lo, 0);
  return [lo, hi];
}}

function fmt(v) {{
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
}}

function selectedTickers(name) {{
  return Array.prototype.slice.call(document.querySelectorAll('input[name="' + name + '"]:checked'))
    .map(function(el) {{ return el.value; }});
}}

function renderScatter(svg, points, xLabel, yLabel) {{
  const width = 720, height = 440;
  const margin = {{top: 20, right: 20, bottom: 46, left: 62}};
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const xs = points.map(function(p) {{ return p.x; }});
  const ys = points.map(function(p) {{ return p.y; }});
  const xr = niceRange(xs), yr = niceRange(ys);
  const xlo = xr[0], xhi = xr[1], ylo = yr[0], yhi = yr[1];

  function xPos(x) {{ return margin.left + (x - xlo) / (xhi - xlo) * plotW; }}
  function yPos(y) {{ return margin.top + (1 - (y - ylo) / (yhi - ylo)) * plotH; }}

  let out = "";
  const nTicks = 5;
  for (let i = 0; i <= nTicks; i++) {{
    const gx = margin.left + plotW * i / nTicks;
    const xVal = xlo + (xhi - xlo) * i / nTicks;
    out += '<line x1="' + gx.toFixed(1) + '" y1="' + margin.top + '" x2="' + gx.toFixed(1) + '" y2="' + (margin.top + plotH) + '" class="chart-grid" />';
    out += '<text x="' + gx.toFixed(1) + '" y="' + (margin.top + plotH + 18) + '" class="chart-tick" text-anchor="middle">' + fmt(xVal) + '</text>';
    const gy = margin.top + plotH * i / nTicks;
    const yVal = yhi - (yhi - ylo) * i / nTicks;
    out += '<line x1="' + margin.left + '" y1="' + gy.toFixed(1) + '" x2="' + (margin.left + plotW) + '" y2="' + gy.toFixed(1) + '" class="chart-grid" />';
    out += '<text x="' + (margin.left - 8) + '" y="' + (gy + 4).toFixed(1) + '" class="chart-tick" text-anchor="end">' + fmt(yVal) + '</text>';
  }}

  const byTicker = {{}};
  points.forEach(function(p) {{ (byTicker[p.ticker] = byTicker[p.ticker] || []).push(p); }});
  Object.keys(byTicker).forEach(function(ticker) {{
    const pts = byTicker[ticker].sort(function(a, b) {{ return a.quarter < b.quarter ? -1 : 1; }});
    const color = colorFor(ticker);
    let path = "";
    pts.forEach(function(p, i) {{
      path += (i === 0 ? "M" : "L") + xPos(p.x).toFixed(1) + "," + yPos(p.y).toFixed(1) + " ";
    }});
    out += '<path d="' + path + '" fill="none" stroke="' + color + '" stroke-width="1" opacity="0.45" />';
    pts.forEach(function(p, i) {{
      const isLast = i === pts.length - 1;
      out += '<circle cx="' + xPos(p.x).toFixed(1) + '" cy="' + yPos(p.y).toFixed(1) + '" r="' + (isLast ? 5 : 3) +
        '" fill="' + color + '" opacity="' + (isLast ? 1 : 0.55) + '"><title>' + p.ticker + ' ' + p.quarter + ': (' + fmt(p.x) + ', ' + fmt(p.y) + ')</title></circle>';
    }});
    const last = pts[pts.length - 1];
    out += '<text x="' + xPos(last.x).toFixed(1) + '" y="' + (yPos(last.y) - 10).toFixed(1) + '" class="chart-label" text-anchor="middle" fill="' + color + '">' + ticker + '</text>';
  }});

  out += '<text x="' + (margin.left + plotW / 2).toFixed(1) + '" y="' + (height - 6) + '" class="chart-axis-title" text-anchor="middle">' + xLabel + '</text>';
  const ylabY = margin.top + plotH / 2;
  out += '<text x="14" y="' + ylabY.toFixed(1) + '" class="chart-axis-title" text-anchor="middle" transform="rotate(-90 14 ' + ylabY.toFixed(1) + ')">' + yLabel + '</text>';

  svg.setAttribute("viewBox", "0 0 " + width + " " + height);
  svg.innerHTML = out;
}}

function renderTrend(svg, seriesByTicker, allQuarters, yLabel) {{
  const width = 760, height = 440;
  const margin = {{top: 20, right: 20, bottom: 60, left: 62}};
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const allValues = [];
  Object.keys(seriesByTicker).forEach(function(t) {{
    Object.keys(seriesByTicker[t]).forEach(function(q) {{ allValues.push(seriesByTicker[t][q]); }});
  }});
  const yr = niceRange(allValues);
  const ylo = yr[0], yhi = yr[1];

  function xPos(idx) {{
    return allQuarters.length <= 1 ? margin.left + plotW / 2 : margin.left + plotW * idx / (allQuarters.length - 1);
  }}
  function yPos(y) {{ return margin.top + (1 - (y - ylo) / (yhi - ylo)) * plotH; }}

  let out = "";
  const nTicks = 5;
  for (let i = 0; i <= nTicks; i++) {{
    const gy = margin.top + plotH * i / nTicks;
    const yVal = yhi - (yhi - ylo) * i / nTicks;
    out += '<line x1="' + margin.left + '" y1="' + gy.toFixed(1) + '" x2="' + (margin.left + plotW) + '" y2="' + gy.toFixed(1) + '" class="chart-grid" />';
    out += '<text x="' + (margin.left - 8) + '" y="' + (gy + 4).toFixed(1) + '" class="chart-tick" text-anchor="end">' + fmt(yVal) + '</text>';
  }}
  const xLabelStep = Math.max(1, Math.ceil(allQuarters.length / 9));
  allQuarters.forEach(function(q, i) {{
    if (i % xLabelStep === 0 || i === allQuarters.length - 1) {{
      out += '<text x="' + xPos(i).toFixed(1) + '" y="' + (margin.top + plotH + 20) + '" class="chart-tick" text-anchor="middle" transform="rotate(45 ' + xPos(i).toFixed(1) + ' ' + (margin.top + plotH + 20) + ')">' + q + '</text>';
    }}
  }});

  Object.keys(seriesByTicker).forEach(function(ticker) {{
    const series = seriesByTicker[ticker];
    const color = colorFor(ticker);
    const pts = [];
    allQuarters.forEach(function(q, i) {{
      if (series[q] !== undefined) pts.push({{i: i, v: series[q], q: q}});
    }});
    if (pts.length === 0) return;
    let path = "";
    pts.forEach(function(p, i) {{ path += (i === 0 ? "M" : "L") + xPos(p.i).toFixed(1) + "," + yPos(p.v).toFixed(1) + " "; }});
    out += '<path d="' + path + '" fill="none" stroke="' + color + '" stroke-width="2" />';
    pts.forEach(function(p) {{
      out += '<circle cx="' + xPos(p.i).toFixed(1) + '" cy="' + yPos(p.v).toFixed(1) + '" r="3" fill="' + color + '"><title>' + ticker + ' ' + p.q + ': ' + fmt(p.v) + '</title></circle>';
    }});
    const lastPt = pts[pts.length - 1];
    out += '<text x="' + (xPos(lastPt.i) + 6).toFixed(1) + '" y="' + yPos(lastPt.v).toFixed(1) + '" class="chart-label" fill="' + color + '">' + ticker + '</text>';
  }});

  out += '<text x="' + (margin.left + plotW / 2).toFixed(1) + '" y="' + (height - 4) + '" class="chart-axis-title" text-anchor="middle">분기</text>';
  const ylabY = margin.top + plotH / 2;
  out += '<text x="14" y="' + ylabY.toFixed(1) + '" class="chart-axis-title" text-anchor="middle" transform="rotate(-90 14 ' + ylabY.toFixed(1) + ')">' + yLabel + '</text>';

  svg.setAttribute("viewBox", "0 0 " + width + " " + height);
  svg.innerHTML = out;
}}

function updateScatterChart() {{
  const xMetric = document.getElementById("scatter-x").value;
  const yMetric = document.getElementById("scatter-y").value;
  const tickers = selectedTickers("scatter-ticker");
  const points = [];
  tickers.forEach(function(ticker) {{
    const series = CHART_DATA[ticker] || {{}};
    Object.keys(series).forEach(function(quarter) {{
      const m = series[quarter];
      if (m[xMetric] !== undefined && m[yMetric] !== undefined) {{
        points.push({{x: m[xMetric], y: m[yMetric], ticker: ticker, quarter: quarter}});
      }}
    }});
  }});
  const svg = document.getElementById("scatter-svg");
  const note = document.getElementById("scatter-empty-note");
  if (points.length === 0) {{
    svg.innerHTML = "";
    note.style.display = "block";
  }} else {{
    note.style.display = "none";
    renderScatter(svg, points, METRIC_LABELS[xMetric], METRIC_LABELS[yMetric]);
  }}
}}

function updateTrendChart() {{
  const yMetric = document.getElementById("trend-y").value;
  const tickers = selectedTickers("trend-ticker");
  const seriesByTicker = {{}};
  const quarterSet = {{}};
  tickers.forEach(function(ticker) {{
    const series = CHART_DATA[ticker] || {{}};
    const s = {{}};
    Object.keys(series).forEach(function(quarter) {{
      const m = series[quarter];
      if (m[yMetric] !== undefined) {{
        s[quarter] = m[yMetric];
        quarterSet[quarter] = true;
      }}
    }});
    if (Object.keys(s).length > 0) seriesByTicker[ticker] = s;
  }});
  const allQuarters = Object.keys(quarterSet).sort();
  const svg = document.getElementById("trend-svg");
  const note = document.getElementById("trend-empty-note");
  if (allQuarters.length === 0) {{
    svg.innerHTML = "";
    note.style.display = "block";
  }} else {{
    note.style.display = "none";
    renderTrend(svg, seriesByTicker, allQuarters, METRIC_LABELS[yMetric]);
  }}
}}

document.querySelectorAll("#scatter-controls select, #scatter-controls input").forEach(function(el) {{
  el.addEventListener("change", updateScatterChart);
}});
document.querySelectorAll("#trend-controls select, #trend-controls input").forEach(function(el) {{
  el.addEventListener("change", updateTrendChart);
}});

updateScatterChart();
updateTrendChart();
"""


def build_summary_report(tickers: list[str], stale_tickers: list[str] | None = None) -> Path:
    stale_set = set(stale_tickers or [])
    rows = []
    for ticker in tickers:
        info = _load_ticker_summary(ticker)
        info["is_stale"] = ticker in stale_set
        rows.append(info)

    chart_data = _collect_quarterly_timeseries(tickers)
    chart_tickers = sorted(chart_data.keys())

    html = PAGE_TEMPLATE.format(
        css=CSS,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        ticker_count=len(tickers),
        table=_build_table_html(rows),
        scatter_x_options=_build_metric_options(default="pe_ttm"),
        scatter_y_options=_build_metric_options(default="roe_ttm"),
        scatter_ticker_checkboxes=_build_ticker_checkboxes(chart_tickers, name="scatter-ticker"),
        trend_y_options=_build_metric_options(default="fcf_ttm"),
        trend_ticker_checkboxes=_build_ticker_checkboxes(chart_tickers, name="trend-ticker"),
        chart_js=_build_chart_js(chart_data, chart_tickers),
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "summary_report.html"
    out_path.write_text(html)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="reports/ 폴더의 모든 티커 리포트를 모아 요약 대시보드 생성"
    )
    parser.add_argument(
        "--check-stale",
        action="store_true",
        help="요약을 만들지 않고, 최근 실행이 오래된(기본 30일) 티커 목록만 출력",
    )
    parser.add_argument("--staleness-days", type=int, default=archive.STALENESS_DAYS)
    args = parser.parse_args()

    tickers = archive.discover_tickers()
    if not tickers:
        print(
            "reports/ 폴더에 티커 리포트가 없습니다. 먼저 개별 티커 리포트를 생성하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    stale = archive.list_stale_tickers(tickers, staleness_days=args.staleness_days)

    if args.check_stale:
        if stale:
            for t in stale:
                print(t)
        else:
            print(f"모든 티커가 최신 상태입니다 ({args.staleness_days}일 이내).")
        return

    out_path = build_summary_report(tickers, stale)
    print(f"요약 리포트 생성 완료: {out_path}")
    if stale:
        print(
            f"[참고] {len(stale)}개 티커가 {args.staleness_days}일 이상 갱신되지 않았습니다: "
            f"{', '.join(stale)}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
