"""Renders a Markdown report (reports/{TICKER}_report.md) as a clean,
self-contained HTML page (reports/{TICKER}_report.html) — no server, no JS,
just open it in a browser.

    python render_html.py AAPL
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import markdown

REPORTS_DIR = Path(__file__).parent / "reports"

DISCLAIMER_MARK = "⚠️"

PAGE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<article class="report">
{body}
</article>
</body>
</html>
"""

CSS = """
:root {
  color-scheme: light dark;
  --bg: #ffffff;
  --fg: #1a1a1a;
  --muted: #5b6470;
  --border: #e2e5e9;
  --card-bg: #f7f8fa;
  --disclaimer-bg: #fff7e6;
  --disclaimer-border: #f0b429;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14161a;
    --fg: #e8eaed;
    --muted: #9aa4b2;
    --border: #2b2f36;
    --card-bg: #1c1f25;
    --disclaimer-bg: #2a2210;
    --disclaimer-border: #a67c00;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Pretendard, "Apple SD Gothic Neo",
               "Noto Sans KR", sans-serif;
  line-height: 1.7;
}
.report {
  max-width: 760px;
  margin: 0 auto;
  padding: 48px 24px 80px;
}
h1 { font-size: 1.75rem; margin: 0 0 8px; }
h2 {
  font-size: 1.35rem;
  margin: 40px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
h3 { font-size: 1.1rem; margin: 28px 0 10px; }
p { margin: 0 0 14px; }
ul, ol { margin: 0 0 14px; padding-left: 1.4em; }
li { margin-bottom: 6px; }
strong { font-weight: 600; }
hr { border: none; border-top: 1px solid var(--border); margin: 32px 0; }

blockquote {
  margin: 0 0 16px;
  padding: 8px 16px;
  border-left: 3px solid var(--border);
  color: var(--muted);
  font-size: 0.92rem;
}
blockquote p { margin: 0; }

table {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 20px;
  font-size: 0.95rem;
}
th, td {
  text-align: left;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}
th { color: var(--muted); font-weight: 600; background: var(--card-bg); }
tr:last-child td { border-bottom: none; }

/* The disclaimer is the first and last blockquote-like paragraph — it starts
   with the warning emoji, so style any paragraph starting with it. */
p.disclaimer {
  background: var(--disclaimer-bg);
  border: 1px solid var(--disclaimer-border);
  border-radius: 8px;
  padding: 14px 16px;
  font-size: 0.92rem;
  color: var(--fg);
}

code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.9em; }
"""


def _mark_disclaimer_paragraphs(html: str) -> str:
    """Tag the disclaimer paragraph(s) with a class so CSS can style them,
    without depending on a specific Markdown extension."""
    return re.sub(
        r"<p>(\s*" + re.escape(DISCLAIMER_MARK) + r".*?)</p>",
        r'<p class="disclaimer">\1</p>',
        html,
        flags=re.DOTALL,
    )


def render_report_html(ticker: str) -> Path:
    ticker = ticker.upper()
    md_path = REPORTS_DIR / f"{ticker}_report.md"
    if not md_path.exists():
        raise FileNotFoundError(
            f"{md_path} not found — generate the Markdown report first "
            f"(ask Claude Code to analyze {ticker}, or run the cfo-report-writer step)."
        )

    md_text = md_path.read_text()
    body_html = markdown.markdown(md_text, extensions=["tables"])
    body_html = _mark_disclaimer_paragraphs(body_html)

    title_match = re.search(r"^##\s+(.+)$", md_text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else f"{ticker} 리포트"

    html = PAGE_TEMPLATE.format(title=title, css=CSS, body=body_html)

    out_path = REPORTS_DIR / f"{ticker}_report.html"
    out_path.write_text(html)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Markdown 리포트를 HTML로 렌더링")
    parser.add_argument("tickers", nargs="+", help="예: AAPL NVDA")
    args = parser.parse_args()

    for ticker in args.tickers:
        try:
            out_path = render_report_html(ticker)
            print(f"{ticker}: {out_path}")
        except FileNotFoundError as exc:
            print(f"[오류] {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
