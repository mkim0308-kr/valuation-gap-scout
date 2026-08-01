"""Capital-allocation agent: how management has actually split cash between
CapEx, R&D, buybacks, dividends, and M&A over the trailing years, sourced
from SEC 10-K XBRL facts (real filings, not estimates). Deterministic, no
LLM — this is a tally, not a judgment of whether the mix is good.
"""
from __future__ import annotations

from quant.sec_data import CAPEX_TAGS, get_annual_xbrl_series

RD_TAGS = ["ResearchAndDevelopmentExpense"]
BUYBACK_TAGS = ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfCapitalStock"]
DIVIDEND_TAGS = ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"]
MA_TAGS = ["PaymentsToAcquireBusinessesNetOfCashAcquired"]


def compute_allocation_mix(totals: dict[str, float]) -> dict[str, float | None]:
    """Each category's share of total capital deployed across categories
    (0-100). None for every category if nothing was deployed at all."""
    total_sum = sum(v for v in totals.values() if v)
    if total_sum <= 0:
        return {k: None for k in totals}
    return {k: round((v or 0) / total_sum * 100, 2) for k, v in totals.items()}


def _trim_to_recent_years(series: dict[int, float], years: int) -> dict[int, float]:
    return dict(sorted(series.items())[-years:])


def get_capital_allocation_history(ticker: str, years: int = 10) -> dict:
    ticker = ticker.upper()

    capex = _trim_to_recent_years(get_annual_xbrl_series(ticker, CAPEX_TAGS), years)
    rd = _trim_to_recent_years(get_annual_xbrl_series(ticker, RD_TAGS), years)
    buybacks = _trim_to_recent_years(get_annual_xbrl_series(ticker, BUYBACK_TAGS), years)
    dividends = _trim_to_recent_years(get_annual_xbrl_series(ticker, DIVIDEND_TAGS), years)
    ma = _trim_to_recent_years(get_annual_xbrl_series(ticker, MA_TAGS), years)

    totals = {
        "capex": sum(capex.values()),
        "rd": sum(rd.values()),
        "buybacks": sum(buybacks.values()),
        "dividends": sum(dividends.values()),
        "ma": sum(ma.values()),
    }
    mix_pct = compute_allocation_mix(totals)

    return {
        "ticker": ticker,
        "years_covered": {
            "capex": sorted(capex.keys()),
            "rd": sorted(rd.keys()),
            "buybacks": sorted(buybacks.keys()),
            "dividends": sorted(dividends.keys()),
            "ma": sorted(ma.keys()),
        },
        "totals": totals,
        "allocation_mix_pct": mix_pct,
        "method": "Sum of each category's SEC 10-K XBRL cash-flow figures over the years "
        "available (up to the trailing N), as a share of the total deployed across all five "
        "categories. Different tags have different filing history, so category year-ranges "
        "may not fully overlap — see years_covered.",
    }
