"""Aggregates every ticker currently in reports/ into one dashboard page:
reports/summary_report.html — a table with links to each ticker's full
report, plus a most-recent ROE vs P/E scatter chart. Reads only what's
already on disk; never runs the pipeline itself (that stays a deliberate,
manual — or Claude-Code-orchestrated — step, since the interpretive agents
can't run headlessly without reintroducing API billing).

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

.chart-wrap { max-width: 640px; }
.roe-pe-chart { width: 100%; height: auto; }
.chart-grid { stroke: var(--border); stroke-width: 1; }
.chart-tick { fill: var(--muted); font-size: 11px; }
.chart-axis-title { fill: var(--muted); font-size: 12px; }
.chart-dot { fill: var(--accent); stroke: var(--bg); stroke-width: 1.5; }
.chart-label { fill: var(--fg); font-size: 11px; font-weight: 600; }
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
<h2>최근 ROE vs P/E</h2>
<div class="chart-wrap">
{chart}
</div>
<p class="muted" style="margin-top:32px; font-size:0.85rem;">
⚠️ 본 페이지는 정보 제공 목적의 정량적 밸류에이션 요약이며, 투자 자문이나 매수/매도 추천이 아닙니다.
</p>
</div>
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


def _build_roe_pe_scatter_svg(points: list[dict], width: int = 640, height: int = 420) -> str:
    """points: [{"ticker": str, "pe": float, "roe": float}, ...], both
    already filtered to non-None, positive P/E. Hand-rolled SVG (no
    matplotlib dependency) so the page stays a single self-contained file."""
    if not points:
        return '<p class="muted">ROE·P/E 데이터가 모두 있는 티커가 없어 차트를 그릴 수 없습니다.</p>'

    margin = {"top": 20, "right": 20, "bottom": 44, "left": 56}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    pes = [p["pe"] for p in points]
    roes = [p["roe"] for p in points]
    pe_min, pe_max = min(pes), max(pes)
    roe_min, roe_max = min(roes), max(roes)
    pe_pad = (pe_max - pe_min) * 0.15 or max(pe_max, 1) * 0.15
    roe_pad = (roe_max - roe_min) * 0.15 or 0.02
    pe_lo, pe_hi = pe_min - pe_pad, pe_max + pe_pad
    roe_lo, roe_hi = roe_min - roe_pad, roe_max + roe_pad
    # P/E padding shouldn't manufacture a negative axis floor when every
    # actual data point is non-negative (an outlier like a 280x P/E just
    # needs a wide axis, not a fake negative P/E gridline).
    if pe_min >= 0:
        pe_lo = max(pe_lo, 0)

    def x_pos(pe: float) -> float:
        return margin["left"] + (pe - pe_lo) / (pe_hi - pe_lo) * plot_w

    def y_pos(roe: float) -> float:
        return margin["top"] + (1 - (roe - roe_lo) / (roe_hi - roe_lo)) * plot_h

    n_ticks = 5
    grid = []
    for i in range(n_ticks + 1):
        gx = margin["left"] + plot_w * i / n_ticks
        pe_val = pe_lo + (pe_hi - pe_lo) * i / n_ticks
        grid.append(
            f'<line x1="{gx:.1f}" y1="{margin["top"]}" x2="{gx:.1f}" '
            f'y2="{margin["top"] + plot_h}" class="chart-grid" />'
            f'<text x="{gx:.1f}" y="{margin["top"] + plot_h + 18}" class="chart-tick" '
            f'text-anchor="middle">{pe_val:.0f}</text>'
        )
        gy = margin["top"] + plot_h * i / n_ticks
        roe_val = roe_hi - (roe_hi - roe_lo) * i / n_ticks
        grid.append(
            f'<line x1="{margin["left"]}" y1="{gy:.1f}" '
            f'x2="{margin["left"] + plot_w}" y2="{gy:.1f}" class="chart-grid" />'
            f'<text x="{margin["left"] - 8}" y="{gy + 4:.1f}" class="chart-tick" '
            f'text-anchor="end">{roe_val * 100:.0f}%</text>'
        )

    dots = []
    for p in points:
        cx, cy = x_pos(p["pe"]), y_pos(p["roe"])
        dots.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" class="chart-dot" />'
            f'<text x="{cx:.1f}" y="{cy - 10:.1f}" class="chart-label" '
            f'text-anchor="middle">{p["ticker"]}</text>'
        )

    axis_y_label_y = margin["top"] + plot_h / 2
    return (
        f'<svg viewBox="0 0 {width} {height}" class="roe-pe-chart" role="img" '
        f'aria-label="ROE vs P/E 산점도">'
        f'{"".join(grid)}'
        f'<text x="{margin["left"] + plot_w / 2:.1f}" y="{height - 6}" '
        f'class="chart-axis-title" text-anchor="middle">Trailing P/E</text>'
        f'<text x="14" y="{axis_y_label_y:.1f}" class="chart-axis-title" text-anchor="middle" '
        f'transform="rotate(-90 14 {axis_y_label_y:.1f})">ROE</text>'
        f'{"".join(dots)}'
        f"</svg>"
    )


def build_summary_report(tickers: list[str], stale_tickers: list[str] | None = None) -> Path:
    stale_set = set(stale_tickers or [])
    rows = []
    chart_points = []
    for ticker in tickers:
        info = _load_ticker_summary(ticker)
        info["is_stale"] = ticker in stale_set
        rows.append(info)
        if info["trailing_pe"] and info["roe"] is not None and info["trailing_pe"] > 0:
            chart_points.append({"ticker": ticker, "pe": info["trailing_pe"], "roe": info["roe"]})

    html = PAGE_TEMPLATE.format(
        css=CSS,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        ticker_count=len(tickers),
        table=_build_table_html(rows),
        chart=_build_roe_pe_scatter_svg(chart_points),
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
