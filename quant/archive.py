"""Snapshot archive: every full pipeline run for a ticker gets copied into a
dated history folder (additive, never overwrites the "latest" data/reports
files other modules already read). This is what trend.py compares against,
and what summary_report.py uses to flag stale tickers. Deterministic, no LLM."""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
HISTORY_DATA_DIR = DATA_DIR / "history"
HISTORY_REPORTS_DIR = REPORTS_DIR / "history"

# Reference window for trend comparisons: skip anything more recent than 1
# month (avoids mistaking short-term price noise for a trend) and anything
# older than 6 months (too stale to call a meaningful comparison point).
REFERENCE_MIN_AGE_DAYS = 30
REFERENCE_MAX_AGE_DAYS = 180

# A ticker is "stale" for summary_report.py purposes if its last full run is
# older than this many days.
STALENESS_DAYS = 30


def archive_run(ticker: str, as_of: date | None = None) -> Path:
    """Copy today's data/{TICKER}_*.json and reports/{TICKER}_report.* into
    data/history/{TICKER}/{date}/ and reports/history/{TICKER}/{date}/.
    Safe to call multiple times the same day (overwrites that day's own
    snapshot, never a prior day's)."""
    ticker = ticker.upper()
    as_of = as_of or date.today()

    data_dest = HISTORY_DATA_DIR / ticker / as_of.isoformat()
    reports_dest = HISTORY_REPORTS_DIR / ticker / as_of.isoformat()
    data_dest.mkdir(parents=True, exist_ok=True)
    reports_dest.mkdir(parents=True, exist_ok=True)

    for json_path in DATA_DIR.glob(f"{ticker}_*.json"):
        shutil.copy2(json_path, data_dest / json_path.name)
    for report_path in REPORTS_DIR.glob(f"{ticker}_report.*"):
        shutil.copy2(report_path, reports_dest / report_path.name)

    return data_dest


def list_snapshot_dates(ticker: str) -> list[date]:
    """All dates for which a history snapshot exists for this ticker, sorted
    oldest first."""
    ticker_dir = HISTORY_DATA_DIR / ticker.upper()
    if not ticker_dir.exists():
        return []
    dates = []
    for child in ticker_dir.iterdir():
        if not child.is_dir():
            continue
        try:
            dates.append(date.fromisoformat(child.name))
        except ValueError:
            continue
    return sorted(dates)


def load_reference_snapshot(
    ticker: str,
    as_of: date | None = None,
    min_age_days: int = REFERENCE_MIN_AGE_DAYS,
    max_age_days: int = REFERENCE_MAX_AGE_DAYS,
) -> dict | None:
    """Return the quant.json snapshot dated closest to (but at least
    min_age_days and at most max_age_days before) as_of — the freshest
    snapshot that's still old enough to count as a real comparison point.
    None if no snapshot falls in that window (e.g. the tool hasn't been used
    for a month yet), never fabricated."""
    ticker = ticker.upper()
    as_of = as_of or date.today()

    candidates = [
        d for d in list_snapshot_dates(ticker)
        if min_age_days <= (as_of - d).days <= max_age_days
    ]
    if not candidates:
        return None

    chosen = max(candidates)
    quant_path = HISTORY_DATA_DIR / ticker / chosen.isoformat() / f"{ticker}_quant.json"
    if not quant_path.exists():
        return None

    return {"snapshot_date": chosen.isoformat(), "quant": json.loads(quant_path.read_text())}


def get_last_run_date(ticker: str) -> date | None:
    """Most recent date this ticker was fully run. Falls back to the
    reports/{TICKER}_report.html file's mtime for tickers generated before
    this archive existed (so pre-existing reports aren't treated as if
    they'd never been run)."""
    ticker = ticker.upper()
    snapshot_dates = list_snapshot_dates(ticker)
    if snapshot_dates:
        return snapshot_dates[-1]

    report_path = REPORTS_DIR / f"{ticker}_report.html"
    if report_path.exists():
        return date.fromtimestamp(report_path.stat().st_mtime)
    return None


def list_stale_tickers(
    tickers: list[str], staleness_days: int = STALENESS_DAYS, as_of: date | None = None
) -> list[str]:
    """Tickers with no run, or whose last run is >= staleness_days old."""
    as_of = as_of or date.today()
    stale = []
    for ticker in tickers:
        last_run = get_last_run_date(ticker)
        if last_run is None or (as_of - last_run).days >= staleness_days:
            stale.append(ticker.upper())
    return stale


def discover_tickers() -> list[str]:
    """All tickers that currently have a generated report in reports/ (the
    aggregate summary_report.html itself is excluded, not a ticker)."""
    tickers = {
        path.stem.removesuffix("_report")
        for path in REPORTS_DIR.glob("*_report.html")
        if path.name != "summary_report.html"
    }
    return sorted(tickers)
