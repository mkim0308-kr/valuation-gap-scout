"""SEC EDGAR XBRL data collection: pulls official operating cash flow and
capex history straight from company filings (not estimates).

The FCF series that feeds the DCF (get_5yr_quarterly_fcf_series) is built
from the trailing 5 years of 10-Q/10-K filings rather than 10-K annual
figures alone. Some issuers (NVIDIA is a confirmed real example) simply
never tag a standalone annual (fp=FY) fact for a line item in most years —
only quarterly (10-Q) duration facts exist for those years — so an
annual-only reader silently ends up with a handful of disconnected years
instead of a real history. Reconstructing single-quarter values from the
as-filed YTD-cumulative 10-Q figures (see _derive_single_quarter_series)
avoids that gap. get_annual_xbrl_series (used by capital_allocation.py for
the multi-year capital-allocation-mix breakdown, a different purpose) is
unchanged and still annual-only.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import requests

SEC_HEADERS = {"User-Agent": "auto-research-pipeline research@example.com"}
CIK_CACHE_PATH = Path(__file__).parent.parent / "data" / "_cik_map.json"

OPERATING_CASHFLOW_TAGS = ["NetCashProvidedByUsedInOperatingActivities"]
CAPEX_TAGS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForCapitalImprovements",
    "PaymentsToAcquireProductiveAssets",
]

QUARTERLY_LOOKBACK_YEARS = 5


def _load_cik_map() -> dict:
    if CIK_CACHE_PATH.exists():
        return json.loads(CIK_CACHE_PATH.read_text())
    resp = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=SEC_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    raw = resp.json()
    cik_map = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in raw.values()}
    CIK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CIK_CACHE_PATH.write_text(json.dumps(cik_map))
    return cik_map


def get_cik(ticker: str) -> str | None:
    return _load_cik_map().get(ticker.upper())


def _get_xbrl_concept(cik: str, tag: str) -> dict | None:
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
    resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
    if resp.status_code != 200:
        return None
    return resp.json()


def _annual_series_from_concept(concept_json: dict) -> dict[int, float]:
    """Collapse full-year (FY) 10-K facts into {fiscal_year: value}."""
    series: dict[int, float] = {}
    for unit_facts in concept_json.get("units", {}).values():
        for fact in unit_facts:
            if fact.get("form") != "10-K":
                continue
            if fact.get("fp") != "FY":
                continue
            fy = fact.get("fy")
            if fy is None:
                continue
            series[fy] = fact["val"]
    return series


def _first_available_series(cik: str, tags: list[str]) -> dict[int, float]:
    """Merge annual series across all given tags (setdefault per year), since
    companies sometimes switch which XBRL tag they report a line item under
    partway through their filing history (e.g. Amazon's capex moved from
    PaymentsToAcquirePropertyPlantAndEquipment to PaymentsToAcquireProductiveAssets
    starting FY2018) — using only the first tag with any data would silently
    truncate the series instead of covering the company's full history."""
    merged: dict[int, float] = {}
    for tag in tags:
        concept = _get_xbrl_concept(cik, tag)
        time.sleep(0.15)  # be polite to SEC rate limits
        if concept:
            series = _annual_series_from_concept(concept)
            for year, val in series.items():
                merged.setdefault(year, val)
    return merged


def get_annual_xbrl_series(ticker: str, tags: list[str]) -> dict[int, float]:
    """Public entry point for pulling any us-gaap XBRL tag's annual 10-K
    series for a ticker — {fiscal_year: value}, trying each tag in `tags`
    in order until one has data. Used by any module that needs a raw SEC
    line item beyond the FCF series below (e.g. capital allocation)."""
    cik = get_cik(ticker)
    if not cik:
        return {}
    return _first_available_series(cik, tags)


def _period_facts_from_concept(concept_json: dict) -> dict[tuple[int, str], dict]:
    """Collapse 10-Q/10-K duration facts into one {"val", "end"} fact per
    (fiscal_year, fiscal_period), fp in {Q1, Q2, Q3, FY}. 10-Q figures are
    YTD-cumulative by SEC convention (Q1=3mo, Q2=6mo, Q3=9mo) — turning them
    into single-quarter values happens in _derive_single_quarter_series;
    point-in-time (balance-sheet) items are used as-is by
    get_5yr_quarterly_snapshot_series. 'end' is kept because a caller may
    need the actual calendar date a period ended on (e.g. to look up a
    stock price as of that date). When a later filing restates a prior
    period, keeps whichever fact was filed most recently."""
    latest_filed: dict[tuple[int, str], str] = {}
    facts: dict[tuple[int, str], dict] = {}
    for unit_facts in concept_json.get("units", {}).values():
        for fact in unit_facts:
            if fact.get("form") not in ("10-K", "10-K/A", "10-Q", "10-Q/A"):
                continue
            fp = fact.get("fp")
            fy = fact.get("fy")
            if fp not in ("Q1", "Q2", "Q3", "FY") or fy is None:
                continue
            key = (fy, fp)
            filed = fact.get("filed", "")
            if key not in latest_filed or filed >= latest_filed[key]:
                latest_filed[key] = filed
                facts[key] = {"val": fact["val"], "end": fact.get("end")}
    return facts


def _period_values_from_concept(concept_json: dict) -> dict[tuple[int, str], float]:
    """Same as _period_facts_from_concept but just the value, for callers
    that don't need the period end date."""
    return {key: fact["val"] for key, fact in _period_facts_from_concept(concept_json).items()}


def _derive_single_quarter_series(
    period_values: dict[tuple[int, str], float],
) -> dict[tuple[int, str], float]:
    """Converts YTD-cumulative Q1/Q2/Q3/FY figures into single-quarter
    Q1-Q4 values by differencing (Q2 = Q2_YTD - Q1_YTD, Q3 = Q3_YTD - Q2_YTD,
    Q4 = FY - Q3_YTD). A quarter is only included if both of its required
    inputs are present in the same fiscal year — never guessed."""
    quarters: dict[tuple[int, str], float] = {}
    fiscal_years = {fy for fy, _ in period_values}
    for fy in fiscal_years:
        q1 = period_values.get((fy, "Q1"))
        q2 = period_values.get((fy, "Q2"))
        q3 = period_values.get((fy, "Q3"))
        full_year = period_values.get((fy, "FY"))
        if q1 is not None:
            quarters[(fy, "Q1")] = q1
        if q1 is not None and q2 is not None:
            quarters[(fy, "Q2")] = q2 - q1
        if q2 is not None and q3 is not None:
            quarters[(fy, "Q3")] = q3 - q2
        if q3 is not None and full_year is not None:
            quarters[(fy, "Q4")] = full_year - q3
    return quarters


def _merged_quarterly_series(cik: str, tags: list[str]) -> dict[tuple[int, str], float]:
    """Merge single-quarter series across all given tags (setdefault per
    quarter) — same rationale as get_annual_xbrl_series's tag merge:
    companies can switch which XBRL tag they report a line item under
    partway through their filing history."""
    merged: dict[tuple[int, str], float] = {}
    for tag in tags:
        concept = _get_xbrl_concept(cik, tag)
        time.sleep(0.15)  # be polite to SEC rate limits
        if concept:
            quarters = _derive_single_quarter_series(_period_values_from_concept(concept))
            for key, val in quarters.items():
                merged.setdefault(key, val)
    return merged


def _quarter_label(fy: int, fp: str) -> str:
    return f"{fy}-{fp}"


def get_5yr_quarterly_fcf_series(
    ticker: str, lookback_years: int = QUARTERLY_LOOKBACK_YEARS
) -> dict[str, float]:
    """Returns {"{fiscal_year}-Q{n}": free_cash_flow} for the trailing
    lookback_years, computed per-quarter as Operating Cash Flow - CapEx,
    reconstructed from SEC 10-Q/10-K XBRL facts (see module docstring for
    why quarterly instead of annual-only)."""
    cik = get_cik(ticker)
    if not cik:
        return {}

    ocf_quarters = _merged_quarterly_series(cik, OPERATING_CASHFLOW_TAGS)
    capex_quarters = _merged_quarterly_series(cik, CAPEX_TAGS)

    fcf_quarters: dict[tuple[int, str], float] = {}
    for key, ocf in ocf_quarters.items():
        capex = capex_quarters.get(key)
        if capex is not None:
            fcf_quarters[key] = ocf - abs(capex)

    return _trim_and_label_quarters(fcf_quarters, lookback_years)


def _trim_and_label_quarters(quarters: dict[tuple[int, str], object], lookback_years: int) -> dict:
    """Shared tail end of every get_5yr_quarterly_*_series function: trim to
    the trailing lookback_years and relabel (fy, fp) keys as "{fy}-{fp}"
    strings, chronologically ordered."""
    if not quarters:
        return {}
    max_fy = max(fy for fy, _ in quarters)
    cutoff_fy = max_fy - lookback_years
    trimmed = {k: v for k, v in quarters.items() if k[0] > cutoff_fy}

    quarter_order = {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3}
    ordered_keys = sorted(trimmed.keys(), key=lambda k: (k[0], quarter_order[k[1]]))
    return {_quarter_label(fy, fp): trimmed[(fy, fp)] for fy, fp in ordered_keys}


def get_5yr_quarterly_flow_series(
    ticker: str, tags: list[str], lookback_years: int = QUARTERLY_LOOKBACK_YEARS
) -> dict[str, float]:
    """Generic single-line-item version of get_5yr_quarterly_fcf_series's
    reconstruction, for any flow (income-statement/cash-flow) XBRL concept
    reported YTD-cumulative in 10-Qs — e.g. NetIncomeLoss. Returns
    {"{fiscal_year}-Q{n}": value} for the trailing lookback_years."""
    cik = get_cik(ticker)
    if not cik:
        return {}
    quarters = _merged_quarterly_series(cik, tags)
    return _trim_and_label_quarters(quarters, lookback_years)


def get_5yr_quarterly_snapshot_series(
    ticker: str, tags: list[str], lookback_years: int = QUARTERLY_LOOKBACK_YEARS
) -> dict[str, float]:
    """Point-in-time series (e.g. StockholdersEquity, shares outstanding)
    for the trailing lookback_years. Unlike get_5yr_quarterly_flow_series,
    no YTD differencing — balance-sheet facts are already a snapshot as of
    each period's end date. The 10-K's FY fact is relabeled Q4 (the fiscal
    year-end snapshot), since SEC XBRL never reports fp='Q4' directly (no
    10-Q is filed for Q4)."""
    cik = get_cik(ticker)
    if not cik:
        return {}
    merged: dict[tuple[int, str], float] = {}
    for tag in tags:
        concept = _get_xbrl_concept(cik, tag)
        time.sleep(0.15)
        if concept:
            for (fy, fp), val in _period_values_from_concept(concept).items():
                merged.setdefault((fy, "Q4" if fp == "FY" else fp), val)
    return _trim_and_label_quarters(merged, lookback_years)


def get_5yr_quarterly_snapshot_dates(
    ticker: str, tags: list[str], lookback_years: int = QUARTERLY_LOOKBACK_YEARS
) -> dict[str, str]:
    """The calendar 'end' date for each quarter in
    get_5yr_quarterly_snapshot_series's series (same tags/window) — e.g. so
    a caller can look up the stock price as of each quarter's end date."""
    cik = get_cik(ticker)
    if not cik:
        return {}
    merged: dict[tuple[int, str], str] = {}
    for tag in tags:
        concept = _get_xbrl_concept(cik, tag)
        time.sleep(0.15)
        if concept:
            for (fy, fp), fact in _period_facts_from_concept(concept).items():
                if fact.get("end"):
                    merged.setdefault((fy, "Q4" if fp == "FY" else fp), fact["end"])
    return _trim_and_label_quarters(merged, lookback_years)


def compute_ttm_series(quarterly_fcf: dict[str, float]) -> dict[str, float]:
    """Rolling trailing-twelve-month sum, one value per quarter that has 3
    consecutive preceding quarters present in the series — a gap in the
    quarter sequence breaks the run rather than summing across the hole."""
    if not quarterly_fcf:
        return {}

    def parse(label: str) -> tuple[int, int]:
        fy, fp = label.split("-")
        return int(fy), int(fp[1])

    def next_quarter(label: str) -> str:
        fy, q = parse(label)
        return f"{fy + 1}-Q1" if q == 4 else f"{fy}-Q{q + 1}"

    ordered = sorted(quarterly_fcf.keys(), key=parse)

    ttm: dict[str, float] = {}
    for i in range(3, len(ordered)):
        window = ordered[i - 3 : i + 1]
        consecutive = all(next_quarter(window[j]) == window[j + 1] for j in range(3))
        if consecutive:
            ttm[ordered[i]] = sum(quarterly_fcf[q] for q in window)
    return ttm


def compute_quarterly_cagr(ttm_series: dict[str, float]) -> float | None:
    """Simple two-point annualized growth rate between the oldest and
    newest TTM FCF value in the series, based on elapsed quarters (n/4
    years). Kept as a secondary/auxiliary figure for comparison — since it
    only looks at the two endpoints, an unusually high or low starting or
    ending TTM point skews it more than compute_ttm_trend_growth_rate's
    regression does. None if fewer than 2 TTM points exist or either
    endpoint isn't positive."""
    if len(ttm_series) < 2:
        return None

    def parse(label: str) -> tuple[int, int]:
        fy, fp = label.split("-")
        return int(fy), int(fp[1])

    ordered = sorted(ttm_series.keys(), key=parse)
    start_label, end_label = ordered[0], ordered[-1]
    start_val, end_val = ttm_series[start_label], ttm_series[end_label]
    if start_val <= 0 or end_val <= 0:
        return None

    start_fy, start_q = parse(start_label)
    end_fy, end_q = parse(end_label)
    elapsed_quarters = (end_fy - start_fy) * 4 + (end_q - start_q)
    if elapsed_quarters <= 0:
        return None
    years = elapsed_quarters / 4
    return (end_val / start_val) ** (1 / years) - 1


def compute_ttm_trend_growth_rate(ttm_series: dict[str, float]) -> float | None:
    """Annualized growth rate from a log-linear (OLS) regression across the
    *entire* TTM series, not just its two endpoints — the primary FCF
    growth-rate figure used elsewhere in the pipeline (DCF's near-term
    growth input, PEG's growth rate). Fits ln(TTM) = a + b*t (t in elapsed
    years) and returns e^b - 1, so a single unusually high or low quarter
    at either end doesn't dominate the estimate the way a 2-point CAGR
    would — the same practical reason a trendline fits better than a
    point-to-point comparison. Degrades gracefully to the same answer as
    compute_quarterly_cagr when there are only 2 points (a line through 2
    points has no other slope to find). None if fewer than 2 points, or any
    TTM value isn't positive (can't take a log of a non-positive FCF)."""
    if len(ttm_series) < 2:
        return None

    def parse(label: str) -> tuple[int, int]:
        fy, fp = label.split("-")
        return int(fy), int(fp[1])

    ordered = sorted(ttm_series.keys(), key=parse)
    values = [ttm_series[label] for label in ordered]
    if any(v <= 0 for v in values):
        return None

    first_fy, first_q = parse(ordered[0])
    xs = []
    for label in ordered:
        fy, q = parse(label)
        elapsed_quarters = (fy - first_fy) * 4 + (q - first_q)
        xs.append(elapsed_quarters / 4)
    ys = [math.log(v) for v in values]

    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_xx = sum(x * x for x in xs)

    denom = n * sum_xx - sum_x**2
    if denom == 0:  # all points at the same elapsed time — no slope to fit
        return None
    slope = (n * sum_xy - sum_x * sum_y) / denom

    return math.exp(slope) - 1


def compute_cagr(series: dict[int, float]) -> float | None:
    """CAGR over the span of an annual value series. Returns None if it can't
    be computed (missing years, non-positive endpoints)."""
    if len(series) < 2:
        return None
    years = sorted(series.keys())
    start_year, end_year = years[0], years[-1]
    start_val, end_val = series[start_year], series[end_year]
    n = end_year - start_year
    if n <= 0 or start_val <= 0 or end_val <= 0:
        return None
    return (end_val / start_val) ** (1 / n) - 1
