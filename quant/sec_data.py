"""SEC EDGAR XBRL data collection: pulls official 10-year operating cash flow
and capex history straight from company filings (not estimates)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

SEC_HEADERS = {"User-Agent": "auto-research-pipeline research@example.com"}
CIK_CACHE_PATH = Path(__file__).parent.parent / "data" / "_cik_map.json"

OPERATING_CASHFLOW_TAGS = ["NetCashProvidedByUsedInOperatingActivities"]
CAPEX_TAGS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForCapitalImprovements",
]


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
    for tag in tags:
        concept = _get_xbrl_concept(cik, tag)
        time.sleep(0.15)  # be polite to SEC rate limits
        if concept:
            series = _annual_series_from_concept(concept)
            if series:
                return series
    return {}


def get_10yr_fcf_series(ticker: str) -> dict[int, float]:
    """Returns {fiscal_year: free_cash_flow} for up to the last 10 fiscal years,
    computed as Operating Cash Flow - CapEx, sourced from SEC 10-K XBRL facts."""
    cik = get_cik(ticker)
    if not cik:
        return {}

    ocf_series = _first_available_series(cik, OPERATING_CASHFLOW_TAGS)
    capex_series = _first_available_series(cik, CAPEX_TAGS)

    fcf_series = {}
    for year, ocf in ocf_series.items():
        capex = capex_series.get(year)
        if capex is not None:
            fcf_series[year] = ocf - abs(capex)

    return dict(sorted(fcf_series.items())[-10:])


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
